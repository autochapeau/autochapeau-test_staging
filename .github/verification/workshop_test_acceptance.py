import json
import socket

from odoo import tools
from odoo.tests import loader

assert env.cr.dbname == "autochapeau_prod_test"
expected = {"work_orders": "17.0.1.0.21", "workorder_service_components": "17.0.5.0.0"}
modules = env["ir.module.module"].search([("name", "in", list(expected)), ("state", "=", "installed")])
assert {module.name: module.latest_version for module in modules} == expected
print("TEST_WORKSHOP_MODULE_VERSIONS=" + json.dumps(expected, sort_keys=True), flush=True)

for action in (
    "action_workshop_pending_preparation",
    "action_my_active_workshop_tasks",
    "action_pending_workshop_quality",
):
    assert env.ref("workorder_service_components." + action).exists(), action

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
print("TEST_WORKSHOP_REGRESSION=" + json.dumps(summary, sort_keys=True), flush=True)
assert result.testsRun == 82, summary
assert not (result.failures_count or result.errors_count or result.skipped), summary
