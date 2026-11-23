import json
from odoo import Command

assert env.cr.dbname == "autochapeau_prod_test", "This fixture is TEST-only"
assert env["ir.config_parameter"].sudo().get_param("database.is_neutralized"), "TEST database is not neutralized"
env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (802305123,))
viewer = env["res.users"].sudo().search([("name", "=", "Eng Moamed Said"), ("active", "=", True)], limit=1)
company = viewer.company_id or env.company
qa = env["car.work.order"].sudo().with_company(company).with_context(
    tracking_disable=True, mail_create_nosubscribe=True, mail_notrack=True, no_reset_password=True,
).env
tag = "DEMO TEST | Material Preparation | 2026-11-23"
order = qa["car.work.order"].search([("notes", "=", tag)], limit=1)

if not order:
    warehouse = qa["stock.warehouse"].search([("company_id", "=", company.id), ("branch_id", "!=", False)], limit=1)
    assert warehouse, "No TEST warehouse is linked to a branch"
    branch = warehouse.branch_id
    common = {"company_id": company.id, "branch_id": branch.id}
    staff = qa["hr.employee"].create(dict(common, name="DEMO TEST | Material Technician", is_technician=True))
    customer = qa["res.partner"].create({"name": "DEMO TEST | Material Preparation Customer"})
    car_brand = qa["fleet.vehicle.model.brand"].search([("name", "=", "DEMO TEST")], limit=1)
    if not car_brand:
        car_brand = qa["fleet.vehicle.model.brand"].create({"name": "DEMO TEST"})
    vehicle_model = qa["fleet.vehicle.model"].create({"name": "Material Preparation Car", "brand_id": car_brand.id})
    vehicle = qa["fleet.vehicle"].create({"model_id": vehicle_model.id, "partner_id": customer.id, "license_plate": "DEMO-MP"})
    category = qa["product.category"].create({"name": "DEMO TEST | Preparation Materials", "is_main_material_category": True})
    brand = qa["car.material.brand"].create({"name": "DEMO TEST | Material Supplier"})
    material = qa["product.product"].create({
        "name": "DEMO TEST | Window Tint Film", "detailed_type": "product",
        "categ_id": category.id, "material_brand_id": brand.id,
    })
    service = qa["product.product"].create({"name": "DEMO TEST | Window Tinting", "detailed_type": "service"})
    part = qa["car.part"].create({"name": "DEMO TEST | Rear Window"})
    qa["car.service.part"].create({
        "part_id": part.id, "service_id": service.id,
        "component_ids": [Command.create({"product_id": material.id, "quantity": 1})],
    })
    slot = qa["car.appointment.slot"].create({
        "date": "2099-01-23", "start_hour": 9, "duration": 1, "capacity": 5, "is_available": True,
    })
    vehicle_values = dict(common, partner_id=customer.id, vehicle_id=vehicle.id)
    appointment = qa["car.appointment"].create(dict(vehicle_values, appointment_slot_id=slot.id))
    checkin = qa["car.checkin"].create(dict(vehicle_values, state="done"))
    appointment.car_checkin_id = checkin
    service_values = {"product_id": service.id, "staff_ids": [Command.set(staff.ids)]}
    preparer_group = "workorder_service_components.group_workshop_material_preparer"
    preparer = viewer if viewer and viewer.has_group(preparer_group) else warehouse.workshop_preparer_id
    if preparer and preparer.active and company in preparer.company_ids:
        service_values["material_preparer_id"] = preparer.id
    order = qa["car.work.order"].create(dict(
        vehicle_values, appointment_id=appointment.id, notes=tag,
        service_ids=[Command.create(service_values)],
    ))
    assert order.material_preparation_enabled and not order.material_preparation_ids
    order.action_confirm()

request = order.material_preparation_ids
assert len(request) == 1 and request.line_ids and request.state == "pending"
assert order.state == "confirmed"
assert request.action_open_preparation()["target"] == "new"
assert not order.material_picking_ids
viewer_visible = None
if viewer and viewer.has_group("work_orders.group_workshop_manager"):
    viewer_visible = bool(order.with_user(viewer).visible_material_preparation_ids)
elif viewer and viewer.has_group("workorder_service_components.group_workshop_material_preparer"):
    viewer_visible = bool(order.with_user(viewer).visible_material_preparation_ids)
env.cr.commit()
print("TEST_MATERIAL_PREPARATION_DEMO=" + json.dumps({
    "work_order": order.name, "work_order_id": order.id,
    "preparation_id": request.id, "state": request.state, "parts": len(request.line_ids),
    "assigned": bool(request.user_id), "visible_to_current_viewer": viewer_visible,
}, ensure_ascii=True), flush=True)
