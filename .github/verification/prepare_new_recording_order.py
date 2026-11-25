import json
from odoo import Command

assert env.cr.dbname == "autochapeau_prod_test"
assert str(env["ir.config_parameter"].sudo().get_param("database.is_neutralized")).lower() in ("true", "1")
env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (802305123,))
original = env["car.work.order"].sudo().browse(3419).exists()
assert original and original.name == "WO/03412" and (original.notes or "").startswith("DEMO TEST")
viewer = env["res.users"].sudo().browse(322).exists()
assert viewer and original.material_preparation_ids.user_id == viewer
company = original.company_id
qa = original.with_company(company).with_context(
    tracking_disable=True, mail_create_nosubscribe=True, mail_notrack=True,
).env
original = original.with_env(qa)
warehouse = original._get_branch_warehouse()
material = qa["product.product"].search([("name", "=", "DEMO TEST | Window Tint Film")], limit=1)
assert material and material.material_brand_id
technician = qa["hr.employee"].search([
    ("user_id", "=", viewer.id), ("company_id", "=", company.id), ("is_technician", "=", True),
], limit=1)
assert technician, "No existing technician profile for the recording user in this Test company"

def get_example(title, staff):
    order = qa["car.work.order"].search([("notes", "=", title)], limit=1)
    if order:
        return order
    common = {
        "partner_id": original.partner_id.id, "vehicle_id": original.vehicle_id.id,
        "company_id": company.id, "branch_id": original.branch_id.id,
    }
    appointment = qa["car.appointment"].create(dict(common, appointment_slot_id=original.appointment_id.appointment_slot_id.id))
    appointment.car_checkin_id = qa["car.checkin"].create(dict(common, state="done"))
    order = qa["car.work.order"].create(dict(
        common, appointment_id=appointment.id, notes=title,
        service_ids=[Command.create({
            "product_id": original.service_ids.product_id.id, "staff_ids": [Command.set(staff.ids)],
            "material_preparer_id": viewer.id,
        })],
    ))
    order.action_confirm()
    lines = order.material_preparation_ids.line_ids
    assert len(lines) == 1
    lines.write({"material_brand_id": material.material_brand_id.id, "product_id": material.id})
    assert lines.quantity > 0
    return order

prep = get_example("DEMO TEST | Full Workshop Recording", technician)
assert prep.id == 3422 and prep.name == "WO/03415"
assert prep.state == "confirmed" and prep.material_preparation_ids.state == "pending"
assert viewer.active and viewer.name == "Eng Moamed Said" and company in viewer.company_ids
manager = env.ref("work_orders.group_workshop_manager")
if not viewer.has_group("work_orders.group_workshop_manager"):
    viewer.with_context(no_reset_password=True).write({"groups_id": [Command.link(manager.id)]})
assert viewer.has_group("work_orders.group_workshop_manager")
assert prep.with_user(viewer).with_company(company).visible_material_preparation_ids
prep.with_user(viewer).with_company(company).check_access_rights("write")
prep.service_ids.with_user(viewer).with_company(company).read(["state"])
location = warehouse.lot_stock_id
quants = qa["stock.quant"]
available = quants._get_available_quantity(material, location, allow_negative=True)
required = prep.material_preparation_ids.line_ids.quantity
if available < required:
    quants._update_available_quantity(material, location, required - available)
env.cr.commit()
env.registry.clear_all_caches()
env.registry.signal_changes()
print("TEST_NEW_PREP_RECORDING_ORDER=" + json.dumps({
    "work_order": prep.name, "order_id": prep.id,
    "request_id": prep.material_preparation_ids.id,
    "task_id": prep.service_ids.id,
    "viewer_is_workshop_manager": viewer.has_group("work_orders.group_workshop_manager"),
    "prepare_option_on": warehouse.workshop_stock_warning_only,
}), flush=True)
