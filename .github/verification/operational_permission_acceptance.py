import json
import socket

from odoo import tools
from odoo.tests import loader

assert env.cr.dbname == "autochapeau_prod_test"
expected = {"sale_salesperson_access": "17.0.1.0.1", "workorder_service_components": "17.0.5.0.1"}
modules = env["ir.module.module"].search([("name", "in", list(expected)), ("state", "=", "installed")])
assert {module.name: module.latest_version for module in modules} == expected
print("TEST_OPERATIONAL_PERMISSIONS_MODULE_VERSIONS=" + json.dumps(expected, sort_keys=True), flush=True)

for action in (
    "action_workshop_pending_preparation",
    "action_my_active_workshop_tasks",
    "action_pending_workshop_quality",
):
    assert env.ref("workorder_service_components." + action).exists(), action

from lxml import etree
users_arch = etree.fromstring(env["res.users"].get_view(env.ref("base.view_users_form").id, "form")["arch"])
assert users_arch.xpath("count(//page[@name='operational_access']//tbody/tr)") == 3

tools.config["test_tags"] = "/workorder_service_components"
suite = loader.make_suite(["workorder_service_components"], position="post_install")
connect = socket.socket.connect
connect_ex = socket.socket.connect_ex


def deny_network(sock, address):
    raise RuntimeError("Network connections are disabled in workshop verification")


socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
try:
    result = loader.run_suite(suite)
finally:
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    env.cr.rollback()

summary = {
    "tests": result.testsRun,
    "failures": result.failures_count,
    "errors": result.errors_count,
    "skipped": result.skipped,
}
print("TEST_OPERATIONAL_PERMISSIONS_REGRESSION=" + json.dumps(summary, sort_keys=True), flush=True)
assert result.testsRun == 85, summary
assert not (result.failures_count or result.errors_count or result.skipped), summary
