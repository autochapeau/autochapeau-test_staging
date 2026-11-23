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

prep = get_example("DEMO TEST | Manual Materials Prepared take 3", original.service_ids.staff_ids)
assert prep.state == "confirmed" and prep.material_preparation_ids.state == "pending"
assert prep.with_user(viewer).with_company(company).visible_material_preparation_ids
env.cr.commit()
print("TEST_NEW_PREP_RECORDING_ORDER=" + json.dumps({
    "work_order": prep.name, "order_id": prep.id,
    "request_id": prep.material_preparation_ids.id,
    "prepare_option_on": warehouse.workshop_stock_warning_only,
}), flush=True)
