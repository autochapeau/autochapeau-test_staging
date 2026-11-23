import json
import socket

from lxml import etree

from odoo import tools
from odoo.tests import loader

assert env.cr.dbname == "autochapeau_prod_test"
module = env["ir.module.module"].search([("name", "=", "workorder_service_components")])
assert module.state == "installed" and module.latest_version == "17.0.5.0.4", (module.state, module.latest_version)
warehouse_model = env["stock.warehouse"].sudo()
arch = etree.fromstring(warehouse_model.get_view(env.ref("stock.view_warehouse").id, "form")["arch"])
assert arch.xpath("//field[@name='workshop_stock_warning_only']"), "Existing warehouse checkbox missing"

assert arch.xpath("//field[@name='workshop_allow_stock_shortage_issue']"), "New warehouse checkbox missing"
assert not warehouse_model.with_context(active_test=False).search_count([
    ('workshop_allow_stock_shortage_issue', '=', True),
])
orders = env['car.work.order'].sudo()
view = env.ref('work_orders.car_work_order_view_form')
assert view._get_combined_arch().xpath("//page[@name='material_preparation']"), "Preparation page missing from combined form"
manager = env.ref('work_orders.group_workshop_manager').users.filtered('active')[:1]
if manager:
    manager_form = orders.with_user(manager).get_view(view.id, 'form')
    assert etree.fromstring(manager_form['arch']).xpath("//page[@name='material_preparation']"), "Manager cannot see preparation page"


requests = env['car.workshop.preparation'].sudo()
original_requests = requests.search([])
orders_with_preparation = original_requests.mapped('workorder_id')
for order in orders_with_preparation:
    assert order.visible_material_preparation_ids == order.material_preparation_ids
    assert order.material_preparation_ready == all(
        request.state == 'prepared' for request in order.material_preparation_ids
    )
for request in original_requests.filtered(lambda row: row.state == 'prepared')[:25]:
    assert request.action_open_preparation()['res_id'] == request.id
legacy = orders.search([
    ('material_preparation_enabled', '=', False),
    ('material_preparation_ids', '=', False),
], limit=100)
assert not legacy.mapped('visible_material_preparation_ids')
print('TEST_WORKSHOP_EXISTING_DATA=' + json.dumps({
    'existing_preparation_requests': len(original_requests),
    'prepared_requests': len(original_requests.filtered(lambda row: row.state == 'prepared')),
    'orders_with_preparation': len(orders_with_preparation),
    'legacy_orders_checked': len(legacy),
}, sort_keys=True), flush=True)


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
print("TEST_WORKSHOP_ISSUE_REGRESSION=" + json.dumps(summary, sort_keys=True), flush=True)
assert result.testsRun >= 87, summary
assert not (result.failures_count or result.errors_count or result.skipped), summary
