import json
import socket

from lxml import etree

from odoo import tools
from odoo.tests import loader

assert env.cr.dbname == "autochapeau_prod_test"
module = env["ir.module.module"].search([("name", "=", "workorder_service_components")])
assert module.state == "installed" and module.latest_version == "17.0.5.0.3"
warehouse_model = env["stock.warehouse"].sudo()
arch = etree.fromstring(warehouse_model.get_view(env.ref("stock.view_warehouse").id, "form")["arch"])
assert arch.xpath("//field[@name='workshop_stock_warning_only']")

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
print("TEST_WORKSHOP_BRAND_REGRESSION=" + json.dumps(summary, sort_keys=True), flush=True)
assert result.testsRun == 86, summary
assert not (result.failures_count or result.errors_count or result.skipped), summary
