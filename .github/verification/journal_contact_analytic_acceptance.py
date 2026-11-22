"""Verify the Journal Items and contact-edit release on TEST."""
from collections import Counter
import importlib
import math
import socket

from lxml import etree
from odoo import tools
from odoo.modules.module import get_manifest
from odoo.tests import loader

assert env.cr.dbname == "autochapeau_prod_test"
module = env["ir.module.module"].search([("name", "=", "partner_management")], limit=1)
assert module.state == "installed" and module.latest_version == get_manifest(module.name)["version"] == "17.0.1.6.8"

lines = env["account.move.line"]
action = env.ref("account.action_account_moves_all")
search_view = etree.fromstring(lines.get_view(action.search_view_id.id, "search")["arch"])
for key, field in (("group_by_product_category", "product_category_id"), ("group_by_invoice_user", "invoice_user_id")):
    match = search_view.xpath("//filter[@name=$name]", name=key)
    assert match and field in match[0].get("context") and lines._fields[field].store, key

sample = lines.search([
    ("parent_state", "=", "posted"), ("product_id", "!=", False),
    ("move_id.invoice_user_id", "!=", False),
], limit=100)
assert sample, "TEST has no posted product lines with a salesperson"
expected = Counter()
expected_credit = Counter()
for line in sample:
    key = (line.product_id.categ_id.id, line.move_id.invoice_user_id.id)
    assert (line.product_category_id.id, line.invoice_user_id.id) == key
    expected[key] += 1
    expected_credit[key] += line.credit
for groupby in (["product_category_id", "invoice_user_id"], ["invoice_user_id", "product_category_id"]):
    groups = lines.read_group([("id", "in", sample.ids)], ["credit:sum"], groupby, lazy=False)
    assert len(groups) == len(expected)
    for group in groups:
        key = (group["product_category_id"][0], group["invoice_user_id"][0])
        assert expected[key] == group["__count"]
        assert math.isclose(expected_credit[key], group["credit"], abs_tol=0.01)
print(f"TEST_JOURNAL_GROUPING_OK=true sample={len(sample)} orders=2", flush=True)

user_view = etree.fromstring(env["res.users"].get_view(env.ref("base.view_users_form").id, "form")["arch"])
assert user_view.xpath("//page[@name='professional']//field[@name='can_edit_existing_contacts']")
importlib.import_module("odoo.addons.partner_management.tests.test_contact_edit_permission")
tools.config["test_tags"] = "partner_contact_edit"
suite = loader.make_suite(["partner_management"], position="post_install")
original_connect = socket.socket.connect

def no_network(*args, **kwargs):
    raise RuntimeError("Contact permission tests cannot contact external services")

socket.socket.connect = no_network
try:
    result = loader.run_suite(suite)
finally:
    socket.socket.connect = original_connect
    env.cr.rollback()
assert result.testsRun == 3 and not result.failures_count and not result.errors_count, (
    result.testsRun, result.failures_count, result.errors_count
)
print("TEST_CONTACT_EDIT_AND_CREATION_OK=true tests=3", flush=True)

from odoo import Command

report_module = env["ir.module.module"].search([("name", "=", "account_financial_report")], limit=1)
assert report_module.state == "installed" and report_module.latest_version == get_manifest(report_module.name)["version"] == "17.0.1.6.10"
wizard_model = env["trial.balance.report.wizard"]
wizard_view = etree.fromstring(wizard_model.get_view(view_type="form")["arch"])
assert wizard_view.xpath("//field[@name='analytic_account_id']")
assert wizard_view.xpath("//button[@name='action_view_analytic_journal_items']")

def analytic_ids(line):
    return {int(value) for key in (line.analytic_distribution or {}) for value in key.split(",")}

recent = lines.search([
    ("parent_state", "=", "posted"), ("analytic_distribution", "!=", False),
    ("account_id.internal_group", "in", ["income", "expense"]),
], limit=50)
for candidate in recent:
    accounts = env["account.analytic.account"].browse(analytic_ids(candidate)).exists()
    selected = accounts.filtered(lambda a: a.active and (not a.company_id or a.company_id == candidate.company_id))[:1]
    if selected:
        sample_line = candidate
        break
else:
    raise AssertionError("TEST has no eligible posted analytics sample")

wizard = wizard_model.with_company(sample_line.company_id).create({
    "date_from": sample_line.date, "date_to": sample_line.date,
    "company_id": sample_line.company_id.id, "target_move": "posted",
    "analytic_account_id": selected.id, "journal_ids": [Command.set(sample_line.journal_id.ids)],
    "account_ids": [Command.set(sample_line.account_id.ids)],
})
matched = lines.search(wizard.action_view_analytic_journal_items()["domain"])
expected_lines = lines.search([
    ("company_id", "=", sample_line.company_id.id), ("journal_id", "=", sample_line.journal_id.id),
    ("date", "=", sample_line.date), ("account_id", "=", sample_line.account_id.id),
    ("parent_state", "=", "posted"),
]).filtered(lambda line: selected.id in analytic_ids(line))
assert sample_line in matched and set(matched.ids) == set(expected_lines.ids)
report = env["report.account_financial_report.trial_balance"].with_company(sample_line.company_id)
values = report._get_report_values(wizard, wizard._prepare_report_trial_balance())
assert not values["trial_balance_grouped"]
assert ("analytic_account_ids", "in", [selected.id]) in values["analytic_drilldown_domain"]
env.cr.rollback()
print(f"TEST_ANALYTIC_TRIAL_BALANCE_OK=true matched={len(matched)}", flush=True)
