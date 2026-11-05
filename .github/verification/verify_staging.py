"""Read-only post-upgrade smoke checks; run through Odoo shell on TEST only.

The shell provides ``env``. No financial records are created, posted or edited.
"""
import json

expected = {
    "account_asset_management": "17.0.1.1.0",
    "appointment_management": "17.0.1.1.1",
    "partner_management": "17.0.1.6.0",
    "sale_split_payment": "17.0.1.3.0",
    "account_deferred_revenue": "17.0.1.2.1",
    "sales_region_commission": "17.0.5.0.2",
    "account_move_print": "17.0.1.2.1",
    "commission": "17.0.1.3.0",
}
result = {"database": env.cr.dbname, "modules": {}, "views": [], "reports": {}}
for name, version in expected.items():
    module = env["ir.module.module"].search([("name", "=", name)])
    assert module.state == "installed", (name, module.state)
    assert module.latest_version == version, (name, module.latest_version, version)
    result["modules"][name] = module.latest_version

fields = {"account.journal": ["service_advance_account_id", "collection_fee_enabled"],
    "account.payment": ["collection_net_amount", "transfer_proof_ids", "cash_stage", "cash_holder_name"],
    "sale.order.payment": ["transfer_proof_ids", "cash_holder_name", "provider_payment_confirmed"],
    "sales.commission.target": ["period_type", "date_end", "member_target_ids"],
    "sales.commission.rule": ["tier_ids", "personal_target", "apply_discount_adjustment"],
    "account.move.line": ["is_service_advance", "collection_charge_kind"],
    "crm.team": ["sales_analytic_account_id"],
    "res.partner": ["contact_partner_type"],
    "account.move": ["asset_schedule_entry"]}
for model, names in fields.items():
    assert set(names).issubset(env[model]._fields), (model, names)
    # Registry metadata alone can pass while the website database lacks columns.
    stored = [name for name in names if env[model]._fields[name].store
              and env[model]._fields[name].type not in ("one2many", "many2many")]
    if stored:
        env[model].sudo().search([], limit=1).read(stored)
        env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s", [env[model]._table])
        assert set(stored).issubset({row[0] for row in env.cr.fetchall()}), (model, stored)
types = dict(env["res.partner"]._fields["contact_partner_type"]._description_selection(env))
assert "agency_salesperson" in types and "employee" in types
assert env.ref("sales_region_commission.menu_targets").parent_id == env.ref("sales_region_commission.menu_root")

for model in ("account.asset", "account.journal", "account.payment", "sale.order.payment", "res.partner",
        "sales.commission.rule", "sales.commission.target", "sale.advance.payment.inv", "account.payment.register", "crm.team"):
    view = env[model].get_view(view_type="form")
    assert view["arch"], model
    result["views"].append(model)
assert "sales_analytic_account_id" in env["crm.team"].get_view(view_type="form")["arch"], "The default Sales Team form must expose its analytic account."
assert "create_deferred_service_invoice" in env["sale.order"].get_view(view_type="form")["arch"], "Service orders need a reachable advance invoice action."

for name, model, domain, report in (
    ("invoice", "account.move", [("state", "=", "posted"), ("move_type", "=", "out_invoice")], "account.account_invoices"),
    ("journal", "account.move", [("state", "=", "posted"), ("move_type", "=", "entry")], "account_move_print.action_report_journal_entries")):
    record = env[model].search(domain, order="id desc", limit=1)
    assert record, name
    html, _ = env["ir.actions.report"]._render_qweb_html(report, record.ids)
    assert len(html) > 1000, name
    assert b"ac-brand-footer" in html, (name, "Missing branded header/footer")
    assert env.ref(report).get_paperformat() == env.ref("account_move_print.paperformat_autochapeau"), name
    if name == "journal":
        assert b"ac-lines" in html and b"TOTAL" in html
    else:
        assert b"ac-invoice" in html and b"vehicle_block_info" in html
    result["reports"][name] = {"rendered": True, "bytes": len(html)}

env.cr.rollback()
print("VIDEO_REQUIREMENTS_SMOKE=" + json.dumps(result, sort_keys=True))
