import json
from odoo import Command
from odoo.exceptions import AccessError, UserError

assert env.cr.dbname == "autochapeau_prod_test"
assert str(env["ir.config_parameter"].sudo().get_param("database.is_neutralized")).lower() in ("true", "1")
env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (802305123,))
first = env["car.work.order"].sudo().browse(3416).exists()
request = env["car.workshop.preparation"].sudo().browse(13).exists()
assert first and first.name == "WO/03409" and (first.notes or "").startswith("DEMO TEST")
assert request and request.workorder_id == first and request.state == "pending"
viewer = request.user_id
assert viewer and viewer.name == "Eng Moamed Said"
company = first.company_id
qa = first.with_company(company).with_context(
    lang="en_US", tracking_disable=True, mail_create_nosubscribe=True, mail_notrack=True,
).env
first = first.with_env(qa)
request = request.with_env(qa)
warehouse = first._get_branch_warehouse()
assert not (warehouse.workshop_stock_warning_only or warehouse.workshop_allow_stock_shortage_issue), "The demo warehouse needs both options off"
material = qa["product.product"].search([("name", "=", "DEMO TEST | Window Tint Film")], limit=1)
assert material and material.material_brand_id
def select_material(preparation):
    assert len(preparation.line_ids) == 1
    preparation.line_ids.write({"material_brand_id": material.material_brand_id.id, "product_id": material.id})
    assert preparation.line_ids.quantity > 0

def verify_validation(callback, words):
    try:
        with qa.cr.savepoint():
            callback()
            raise AssertionError("Expected an insufficient stock validation")
    except AccessError:
        raise
    except UserError as error:
        assert all(word in str(error).lower() for word in words), str(error)
        return str(error)

location = warehouse.lot_stock_id
quant = qa["stock.quant"]
assert not quant._get_available_quantity(material, location), "Expected zero available demo stock"
select_material(request)
verify_validation(request.with_user(viewer).action_mark_prepared, ("insufficient",))
label = "DEMO TEST | Finish stock validation | 2026-11-23"
second = qa["car.work.order"].search([("notes", "=", label)], limit=1)
if not second:
    common = {
        "partner_id": first.partner_id.id, "vehicle_id": first.vehicle_id.id,
        "company_id": company.id, "branch_id": first.branch_id.id,
    }
    appointment = qa["car.appointment"].create(dict(common, appointment_slot_id=first.appointment_id.appointment_slot_id.id))
    checkin = qa["car.checkin"].create(dict(common, state="done"))
    appointment.car_checkin_id = checkin
    original_task = first.service_ids
    staff = original_task.staff_ids
    eligible = viewer.employee_ids.filtered(
        lambda employee: employee.company_id == company and employee.branch_id == first.branch_id and employee.is_technician
    )
    second = qa["car.work.order"].create(dict(
        common, appointment_id=appointment.id, notes=label,
        service_ids=[Command.create({
            "product_id": original_task.product_id.id, "staff_ids": [Command.set((staff | eligible).ids)],
            "material_preparer_id": viewer.id,
        })],
    ))
    second.action_confirm()
    prepared = second.material_preparation_ids
    select_material(prepared)
    amount = prepared.line_ids.quantity
    quant._update_available_quantity(material, location, amount)
    prepared.action_mark_prepared()
    second.action_progress()
    second.service_ids.action_start()
    quant._update_available_quantity(material, location, -amount)

task = second.service_ids
assert second.state == task.state == "progress"
assert not quant._get_available_quantity(material, location)
finish_message = verify_validation(task.action_finish, ("insufficient available stock",))
viewer_can_finish = True
try:
    verify_validation(task.with_user(viewer).action_finish, ("insufficient available stock",))
except AccessError:
    viewer_can_finish = False
assert request.state == "pending" and not second.material_picking_ids
env.cr.commit()
print("TEST_STOCK_VALIDATION_DEMO=" + json.dumps({
    "warehouse_id": warehouse.id, "prepare_order": first.name, "prepare_request_id": request.id,
    "finish_order": second.name, "finish_order_id": second.id, "finish_task_id": task.id,
    "viewer_can_finish": viewer_can_finish, "finish_validation": finish_message,
    "viewer_is_workshop_employee": viewer.has_group("work_orders.group_workshop_employee"),
    "viewer_has_technician_profile": bool(viewer.employee_ids.filtered("is_technician")),
}), flush=True)
