"""Verify the Profit and Loss release with disposable layouts and wizard rows."""
from datetime import date
from io import BytesIO
from zipfile import ZipFile

from lxml import etree

addon = "account_balance_sheet_report"
module = env["ir.module.module"].search([("name", "=", addon)], limit=1)
assert module.state == "installed" and module.latest_version == "17.0.1.0.3"

pl_action = env.ref(f"{addon}.action_account_report_pl")
pl_wizards = env[pl_action.res_model].with_context(lang="en_US", discard_logo_check=True)
wizard_arch = etree.fromstring(pl_wizards.get_view(pl_action.view_id.id, "form")["arch"])
assert wizard_arch.xpath("//button[@name='button_view_profit_loss']")
assert env.ref(f"{addon}.menu_profit_loss_layout").action == env.ref(f"{addon}.action_profit_loss_layout")
pl_layouts = env["account.profit.loss.layout"].with_context(lang="en_US")
pl_report = env["account.profit.loss.report"].with_context(lang="en_US")
pl_company = env.company
pl_today = date.today()
pl_start = pl_today.replace(month=1, day=1)

pl_wizard = pl_wizards.create({
    "company_id": pl_company.id,
    "account_report_id": env.ref(f"{addon}.account_financial_report_profitandloss0").id,
    "date_from": pl_start,
    "date_to": pl_today,
})
pl_standard = ["Revenue", "Less Costs of Revenue", "Gross Profit", "Less Operating Expenses",
               "Operating Income (or Loss)", "Plus Other Income", "Less Other Expenses", "Net Profit"]
pl_values = pl_report._get_values(pl_wizard._report_data()["form"])
assert [row["name"] for row in pl_values["rows"]] == pl_standard
pl_scope = [
    ("company_id", "=", pl_company.id), ("parent_state", "=", "posted"),
    ("date", ">=", pl_start), ("date", "<=", pl_today),
    ("account_id.account_type", "in", ["income", "income_other", "expense", "expense_direct_cost", "expense_depreciation"]),
]
if pl_wizard.journal_ids:
    pl_scope.append(("journal_id", "in", pl_wizard.journal_ids.ids))
pl_total = env["account.move.line"]._read_group(pl_scope, [], ["balance:sum"])[0][0] or 0
assert pl_company.currency_id.compare_amounts(pl_values["rows"][-1]["balance"], -pl_total) == 0

pl_layout = pl_layouts.create({"name": "Release verification", "company_id": pl_company.id})
pl_final = pl_layout.line_ids.filtered(lambda line: line.section == "net_profit")
pl_final.write({"sequence": 1, "name": "Release Verification Total"})
pl_wizard.profit_loss_layout_id = pl_layout
pl_preview = pl_wizard.button_view_profit_loss()
assert pl_preview["views"][0][0] == env.ref(f"{addon}.profit_loss_preview_form").id
assert "Release Verification Total" in pl_wizard.profit_loss_preview
assert etree.HTML(pl_wizard.profit_loss_preview).xpath("//tbody/tr[1]/th/span/text()") == ["Release Verification Total"]

pl_pdf = pl_wizard.button_export_pdf()
pl_action_model = env["ir.actions.report"]
pl_pdf_html, _ = pl_action_model.with_context(**pl_pdf["context"])._render_qweb_html(
    pl_pdf["report_name"], pl_wizard.ids, data=pl_pdf["data"],
)
assert b"Release Verification Total" in pl_pdf_html
pl_xlsx = pl_wizard.button_export_xlsx()
pl_xlsx_bytes, _ = pl_action_model.with_context(**pl_xlsx["context"])._render_xlsx(
    pl_xlsx["report_name"], pl_wizard.ids, pl_xlsx["data"],
)
with ZipFile(BytesIO(pl_xlsx_bytes)) as pl_book:
    assert b"Release Verification Total" in pl_book.read("xl/sharedStrings.xml")
    assert etree.fromstring(pl_book.read("xl/worksheets/sheet1.xml")).xpath(
        "//*[local-name()='c'][@r='B6']/*[local-name()='v']"
    )

env.cr.rollback()
print("PROFIT_LOSS_RELEASE_OK=menu,default_order,net_profit,custom_order,preview,pdf_template,xlsx", flush=True)
