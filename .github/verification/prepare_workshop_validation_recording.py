import json

from odoo import Command
from odoo.exceptions import UserError


assert env.cr.dbname == "autochapeau_prod_test"
assert str(env["ir.config_parameter"].sudo().get_param("database.is_neutralized")).lower() in ("true", "1")
env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (802305123,))

source = env["car.work.order"].sudo().browse(3422).exists()
assert source and source.name == "WO/03415" and source.notes == "DEMO TEST | Full Workshop Recording"
viewer = source.material_preparation_ids.user_id
assert viewer and viewer.name == "Eng Moamed Said" and viewer.has_group("work_orders.group_workshop_manager")
company = source.company_id
qa = source.with_company(company).with_context(
    lang="en_US", tracking_disable=True, mail_create_nosubscribe=True, mail_notrack=True,
).env
source = source.with_env(qa)
location = source._get_branch_warehouse().lot_stock_id
tag = "DEMO TEST | Workshop Start and Film Unit Validation"
order = qa["car.work.order"].search([("notes", "=", tag)], limit=1)

if not order:
    category = qa["product.category"].create({"name": "DEMO TEST | PPF Films", "is_main_material_category": True})
    brand = qa["car.material.brand"].create({"name": "DEMO TEST | PPF Supplier"})
    roll_categories = {
        length: qa["uom.category"].create({"name": f"DEMO TEST | Roll {length} m"}) for length in (15, 30)
    }
    rolls = {
        length: qa["uom.uom"].create({
            "name": f"Demo Roll {length} m", "category_id": roll_categories[length].id,
            "uom_type": "reference", "rounding": 0.0001,
        }) for length in roll_categories
    }
    inch = qa["uom.uom"].create({
        "name": "In (DEMO Roll 30 m)", "category_id": roll_categories[30].id,
        "uom_type": "smaller", "factor": 30 / 0.0254, "rounding": 0.01,
    })

    for code, label, length in (
        ("DEMO-PPF-15", "DEMO TEST | PPF Film - Roll 15 m", 15),
        ("DEMO-PPF-30", "DEMO TEST | PPF Film - Roll 30 m", 30),
        ("DEMO-PPF-30-OUT", "DEMO TEST | PPF Film - Roll 30 m Out of Stock", 30),
    ):
        qa["product.product"].create({
            "name": label, "default_code": code, "detailed_type": "product", "categ_id": category.id,
            "material_brand_id": brand.id, "uom_id": rolls[length].id, "uom_po_id": rolls[length].id,
        })

    ppf = qa["product.product"].create({"name": "DEMO TEST | Partial Front PPF (Small)", "detailed_type": "service"})
    for name, quantity in (("Hood", 35), ("Front Fender", 17), ("Front Bumper", 55)):
        part = qa["car.part"].create({"name": f"DEMO TEST | Validation {name}"})
        qa["car.service.part"].create({
            "part_id": part.id, "service_id": ppf.id,
            "component_ids": [Command.create({
                "material_category_id": category.id, "quantity": quantity,
                "product_uom_id": inch.id, "allowed_brand_ids": [Command.link(brand.id)],
            })],
        })

    common = {
        "partner_id": source.partner_id.id, "vehicle_id": source.vehicle_id.id,
        "company_id": company.id, "branch_id": source.branch_id.id,
    }
    appointment = qa["car.appointment"].create(dict(common, appointment_slot_id=source.appointment_id.appointment_slot_id.id))
    appointment.car_checkin_id = qa["car.checkin"].create(dict(common, state="done"))
    order = qa["car.work.order"].create(dict(
        common, appointment_id=appointment.id, notes=tag,
        service_ids=[Command.create({
            "product_id": product.id, "staff_ids": [Command.set(source.service_ids.staff_ids.ids)],
            "material_preparer_id": viewer.id,
        }) for product in (source.service_ids.product_id, ppf)],
    ))
    order.action_confirm()

assert order.state == "confirmed" and len(order.material_preparation_ids) == 2
products = qa["product.product"]
compatible = products.search([("default_code", "=", "DEMO-PPF-30")], limit=1)
incompatible = products.search([("default_code", "=", "DEMO-PPF-15")], limit=1)
out_of_stock = products.search([("default_code", "=", "DEMO-PPF-30-OUT")], limit=1)
tint = products.search([("name", "=", "DEMO TEST | Window Tint Film")], limit=1)
ppf_request = order.material_preparation_ids.filtered(lambda request: "Partial Front PPF" in request.service_id.name)
tint_request = order.material_preparation_ids - ppf_request
assert len(ppf_request.line_ids) == 3 and len(tint_request.line_ids) == 1
assert compatible and incompatible and out_of_stock and tint

quants = qa["stock.quant"]
for material in (compatible, tint):
    available = quants._get_available_quantity(material, location, allow_negative=True)
    if available < 1:
        quants._update_available_quantity(material, location, 1 - available)

ppf_request.line_ids.write({"material_brand_id": compatible.material_brand_id.id})
tint_request.line_ids.write({"material_brand_id": tint.material_brand_id.id, "product_id": tint.id})


def verify_error(callback, message):
    try:
        with qa.cr.savepoint():
            callback()
            raise AssertionError(f"Expected validation: {message}")
    except UserError as error:
        assert message in str(error), str(error)
        return str(error)


as_viewer = order.with_user(viewer)
task = tint_request.task_id.with_user(viewer)
early_start = verify_error(task.action_start, "The workshop manager must start the prepared order")
bad_unit = verify_error(
    lambda: ppf_request.line_ids[0].with_user(viewer).write({"product_id": incompatible.id}),
    "Choose a material compatible with the configured quantity unit",
)


class RollBackDemonstration(Exception):
    pass


try:
    with qa.cr.savepoint():
        line = ppf_request.line_ids[0].with_user(viewer)
        line.write({"product_id": out_of_stock.id})
        assert "Insufficient stock" in line.material_stock_warning
        ppf_request.line_ids.with_user(viewer).write({"product_id": compatible.id})
        as_viewer.material_preparation_ids.action_mark_prepared()
        as_viewer.action_progress()
        task.action_start()
        assert as_viewer.state == task.state == "progress"
        raise RollBackDemonstration()
except RollBackDemonstration:
    pass

assert order.state == "confirmed" and set(order.material_preparation_ids.mapped("state")) == {"pending"}
env.cr.commit()
print("TEST_NEW_PREP_RECORDING_ORDER=" + json.dumps({
    "work_order": order.name, "order_id": order.id, "early_start": early_start,
    "incompatible_unit": bad_unit, "insufficient_stock_warning": True, "repair_verified": True,
}), flush=True)
