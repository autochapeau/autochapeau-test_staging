import json

assert env.cr.dbname == "autochapeau_prod_test", "Only the TEST database may be changed"
assert env["ir.config_parameter"].sudo().get_param("database.is_neutralized").lower() in ("true", "1"), "TEST database must be neutralized"
order = env["car.work.order"].sudo().browse(3416).exists()
request = env["car.workshop.preparation"].sudo().browse(13).exists()
assert order and order.name == "WO/03409" and (order.notes or "").startswith("DEMO TEST | Material Preparation")
assert request and request.workorder_id == order
assert order.state == "confirmed" and request.state == "pending"

viewer = env["res.users"].sudo().search([
    ("name", "=", "Eng Moamed Said"),
    ("active", "=", True),
    ("share", "=", False),
])
assert len(viewer) == 1 and viewer.has_group("base.group_user"), "Expected one active internal TEST user"
company = order.company_id
assert company in viewer.company_ids, "User lacks access to the work order company"
preparer_group = env.ref("workorder_service_components.group_workshop_material_preparer")
existing_groups = viewer.groups_id
if preparer_group not in existing_groups:
    viewer.with_context(no_reset_password=True).write({"operational_material_preparer": True})
assert viewer.groups_id == (existing_groups | preparer_group), "Unexpected permissions changed"
if request.user_id != viewer:
    request.write({"user_id": viewer.id})
assert request.user_id == viewer and request.state == "pending"

order_visible = order.with_user(viewer).with_company(company).read(["visible_material_preparation_ids"])[0]
assert request.id in order_visible["visible_material_preparation_ids"]
action = request.with_user(viewer).with_company(company).action_open_preparation()
assert action["res_id"] == request.id and action["target"] == "new"

view = env.ref("work_orders.car_work_order_view_form")
arch = order.with_user(viewer).with_company(company).get_view(view.id, "form")["arch"]
assert 'name="material_preparation"' in arch

env.cr.commit()
env.registry.clear_all_caches()
env.registry.signal_changes()
print("TEST_MATERIAL_ASSIGNMENT=" + json.dumps({
    "order": order.name, "order_id": order.id, "request_id": request.id,
    "preparer_permission": True, "assigned_to_requested_account": True,
    "tab_visible": True, "state": request.state,
}), flush=True)
