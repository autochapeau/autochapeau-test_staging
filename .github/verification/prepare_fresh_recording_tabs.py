import json
from odoo import Command
from odoo.tools.float_utils import float_compare

assert env.cr.dbname == "autochapeau_prod_test"
assert str(env["ir.config_parameter"].sudo().get_param("database.is_neutralized")).lower() in ("true", "1")
env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (802305123,))
original = env["car.work.order"].sudo().browse(3416).exists()
original_task = env["car.workorder.service"].sudo().browse(5689).exists()
assert original and original.name == "WO/03409" and (original.notes or "").startswith("DEMO TEST")
assert original_task and original_task.workorder_id.name == "WO/03411"
viewer = env["res.users"].sudo().browse(322).exists()
assert viewer and original.material_preparation_ids.user_id == viewer
company = original.company_id
qa = original.with_company(company).with_context(
    tracking_disable=True, mail_create_nosubscribe=True, mail_notrack=True,
).env
original = original.with_env(qa)
warehouse = original._get_branch_warehouse()
material = qa["product.product"].search([("name", "=", "DEMO TEST | Window Tint Film")], limit=1)
assert material and material.material_brand_id and original_task.staff_ids
assert viewer in original_task.staff_ids.user_id
location = warehouse.lot_stock_id
quant = qa["stock.quant"]
stock_before = quant._get_available_quantity(material, location, allow_negative=True)
assert stock_before <= 0, "Expected no available recording stock in the sandbox"

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

prep = get_example("DEMO TEST | Manual Materials Prepared take 2", original.service_ids.staff_ids)
finish = get_example("DEMO TEST | Manual Finish take 2", original_task.staff_ids)
if finish.state == "confirmed":
    preparation = finish.material_preparation_ids
    amount = preparation.line_ids.quantity - stock_before
    quant._update_available_quantity(material, location, amount)
    preparation.action_mark_prepared()
    finish.action_progress()
    finish.service_ids.action_start()
    quant._update_available_quantity(material, location, -amount)

assert prep.state == "confirmed" and prep.material_preparation_ids.state == "pending"
assert finish.state == finish.service_ids.state == "progress" and not finish.service_ids.materials_issued
assert not float_compare(stock_before, quant._get_available_quantity(material, location, allow_negative=True),
                         precision_rounding=material.uom_id.rounding)
assert prep.with_user(viewer).with_company(company).visible_material_preparation_ids
finish.service_ids.with_user(viewer).with_company(company).read(["state"])
env.cr.commit()
print("TEST_FRESH_RECORDING_TABS=" + json.dumps({
    "prep_order": prep.name, "prep_order_id": prep.id,
    "finish_order": finish.name, "finish_task_id": finish.service_ids.id,
    "prepare_option_on": warehouse.workshop_stock_warning_only,
    "finish_option_on": warehouse.workshop_allow_stock_shortage_issue,
}), flush=True)
