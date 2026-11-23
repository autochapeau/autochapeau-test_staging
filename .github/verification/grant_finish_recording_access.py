import json
from odoo import Command
from odoo.exceptions import AccessError, UserError

assert env.cr.dbname == "autochapeau_prod_test"
assert str(env["ir.config_parameter"].sudo().get_param("database.is_neutralized")).lower() in ("true", "1")
env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (802305123,))
viewer = env["res.users"].sudo().browse(322).exists()
previous_request = env["car.workshop.preparation"].sudo().browse(13).exists()
assert viewer and viewer.active and viewer.name == "Eng Moamed Said"
assert previous_request and previous_request.user_id == viewer and previous_request.workorder_id.name == "WO/03409"
task = env["car.workorder.service"].sudo().browse(5689).exists()
assert task and task.state == "progress"
order = task.workorder_id
assert order.id == 3418 and order.name == "WO/03411" and (order.notes or "").startswith("DEMO TEST | Finish stock validation")
assert order.state == "progress" and not task.materials_issued
company = order.company_id
assert company in viewer.company_ids and viewer.has_group("base.group_user")
viewer = viewer.with_company(company)
employee_model = env["hr.employee"].sudo().with_company(company).with_context(
    tracking_disable=True, mail_create_nosubscribe=True, mail_notrack=True,
)
employee = employee_model.with_context(active_test=False).search([
    ("user_id", "=", viewer.id), ("company_id", "=", company.id),
])
assert len(employee) <= 1
if employee:
    assert employee.active, "The linked TEST employee is archived"
    if not employee.is_technician:
        employee.write({"is_technician": True})
else:
    employee = employee_model.create({
        "name": "DEMO TEST | Finish Validation Technician",
        "company_id": company.id, "user_id": viewer.id,
        "is_technician": True, "branch_id": False,
    })
role = env.ref("work_orders.group_workshop_employee")
old_groups = viewer.groups_id
if role not in old_groups:
    viewer.with_context(no_reset_password=True).write({"groups_id": [Command.link(role.id)]})
assert viewer.groups_id == (old_groups | role)
if employee not in task.staff_ids:
    task.with_context(contract_upsell_sync=True, tracking_disable=True, mail_notrack=True).write({"staff_ids": [Command.link(employee.id)]})

task_for_viewer = task.with_user(viewer).with_company(company).with_context(lang="en_US")
task_for_viewer.read(["state", "workorder_id"])
try:
    with env.cr.savepoint():
        task_for_viewer.action_finish()
        raise AssertionError("Finish was expected to be blocked by zero available stock")
except AccessError:
    raise
except UserError as error:
    assert "insufficient available stock" in str(error).lower(), str(error)
    message = str(error)
assert task.state == "progress" and not task.materials_issued
env.cr.commit()
env.registry.clear_all_caches()
env.registry.signal_changes()
print("TEST_FINISH_RECORDING_ACCESS=" + json.dumps({
    "work_order": order.name, "task_id": task.id, "role": "Workshop Employee",
    "assigned_to_recording_user": True, "finish_validation": message,
}), flush=True)
