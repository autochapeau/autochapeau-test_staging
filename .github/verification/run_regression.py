"""Run rollback-only regression tests from outside addon tests directories.

Run with Odoo shell and set VIDEO_VERIFICATION_ROOT to this directory.
External Python network connections are blocked while the suite runs.
"""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import types

from lxml import etree

from odoo import tools
from odoo.tests import loader
from odoo.modules.module import get_module_path

root = Path(os.environ["VIDEO_VERIFICATION_ROOT"]).resolve()
component_module = env["ir.module.module"].search([("name", "=", "workorder_service_components")])
assert component_module.state == "installed" and component_module.latest_version == "17.0.3.2.0"
for model, view in (
    ("product.product", "product.product_normal_form_view"),
    ("product.template", "product.product_template_only_form_view"),
):
    arch = etree.fromstring(env[model].get_view(env.ref(view).id, "form")["arch"])
    tables = arch.xpath("//field[@name='ungrouped_component_ids']")
    assert tables and all(table.get("readonly") == "1" for table in tables), model
services = env["product.product"].with_context(active_test=False).search([("detailed_type", "=", "service")])
assert not services.bom_ids.filtered(lambda bom: not bom.service_part_id)
print("SERVICE_COMPONENTS_REFERENCE_SMOKE=" + json.dumps({
    "version": component_module.latest_version, "readonly_tables": True,
    "services_checked": len(services), "operational_components": len(services.bom_ids),
    "reference_components": env["car.bom"].search_count([("service_part_id", "=", False)]),
}, sort_keys=True))
sources = {
    "account_asset_management": ["test_draft_schedule"],
    "partner_management": ["test_contact_references", "test_team_analytic"],
    "sale_split_payment": ["test_collection_fees", "test_cash_custody", "test_payment_attachment"],
    "account_deferred_revenue": ["test_service_advance"],
    "sales_region_commission": ["test_commission", "test_accounting", "test_user_access", "test_target_tiers"],
    "workorder_service_components": ["test_service_materials"],
}
for addon, names in sources.items():
    name = "odoo.addons." + addon + ".tests"
    path = root / "addon_tests" / addon
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    package.__spec__ = importlib.util.spec_from_loader(name, loader=None, is_package=True)
    sys.modules[name] = package
    for leaf in names:
        full_name = name + "." + leaf
        source = path / (leaf + ".py")
        if leaf == "test_payment_attachment" or addon == "workorder_service_components":
            source = Path(get_module_path(addon)) / "tests" / (leaf + ".py")
        spec = importlib.util.spec_from_file_location(full_name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)
        setattr(package, leaf, module)

tools.config["test_tags"] = "asset_draft_schedule,contact_reference_types,team_analytic_sales,collection_fees_proof,payment_attachment,cash_custody_flow,service_advance_flow,/sales_region_commission,/workorder_service_components"
suite = loader.make_suite(list(sources), position="post_install")
original_connect = socket.socket.connect

def no_external_python_network(sock, address):
    raise RuntimeError("Verification transaction: external network disabled")

socket.socket.connect = no_external_python_network
try:
    result = loader.run_suite(suite)
finally:
    socket.socket.connect = original_connect
    env.cr.rollback()

summary = {"database": env.cr.dbname, "tests": result.testsRun,
    "failures": result.failures_count, "errors": result.errors_count, "skipped": result.skipped}
print("VIDEO_REQUIREMENTS_REGRESSION=" + json.dumps(summary, sort_keys=True))
assert result.testsRun >= 244, summary
assert result.failures_count == 0 and result.errors_count == 0 and result.skipped == 0, summary
