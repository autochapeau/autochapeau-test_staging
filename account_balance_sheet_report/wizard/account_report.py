from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import get_lang


class AccountingReport(models.TransientModel):
    show_analytic_account = fields.Boolean(string="Analytic Account")
    _name = "accounting.reporting"
    _description = "Accounting Reporting"

    @api.model
    def _get_account_report(self):
        reports = []
        if self._context.get("active_id"):
            menu = self.env["ir.ui.menu"].browse(
                self._context.get("active_id")).name
            reports = self.env["account.financial.report"].search(
                [("name", "ilike", menu)])
        return reports and reports[0] or False

    enable_filter = fields.Boolean(string="Enable Comparison")
    target_move = fields.Selection(
        [("posted", "All Posted Entries"), ("all", "All Entries")],
        string="Target Moves",
        required=True,
        default="posted",
    )
    account_report_id = fields.Many2one(
        "account.financial.report",
        string="Account Reports",
        required=True,
        default=_get_account_report,
    )
    label_filter = fields.Char(
        string="Column Label",
        help="This label will be displayed on report to show the balance computed " "for the given comparison filter.",
    )
    filter_cmp = fields.Selection(
        [("filter_no", "No Filters"), ("filter_date", "Date")],
        string="Filter by",
        required=True,
        default="filter_no",
    )
    date_from_cmp = fields.Date(string="Start Date Compare")
    date_to_cmp = fields.Date(string="End Date Compare")
    debit_credit = fields.Boolean(
        string="Display Debit/Credit Columns",
        help="This option allows you to get more details about the way your balances "
        "are computed. Because it is space consuming, we do not allow to use it "
        "while doing a comparison.",
    )
    date_from = fields.Date(string="Start Date")
    date_to = fields.Date(string="End Date")
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, readonly=True, default=lambda self: self.env.company
    )
    journal_ids = fields.Many2many(
        comodel_name="account.journal",
        string="Journals",
        required=True,
        default=lambda self: self.env["account.journal"].search(
            [("company_id", "=", self.company_id.id)]),
        domain="[('company_id', '=', company_id)]",
    )
    analytic_account_ids = fields.Many2many(
        comodel_name="account.analytic.account",
        string="Analytic Accounts",
    )

    def _build_comparison_context(self, data):
        result = {}
        result["journal_ids"] = "journal_ids" in data["form"] and data["form"]["journal_ids"] or False
        result["state"] = "target_move" in data["form"] and data["form"]["target_move"] or ""
        if data["form"]["filter_cmp"] == "filter_date":
            result["date_from"] = data["form"]["date_from_cmp"]
            result["date_to"] = data["form"]["date_to_cmp"]
            result["strict_range"] = True
        return result

    def _build_contexts(self, data):
        result = {}
        result["journal_ids"] = "journal_ids" in data["form"] and data["form"]["journal_ids"] or False
        result["state"] = "target_move" in data["form"] and data["form"]["target_move"] or ""
        result["date_from"] = data["form"]["date_from"] or False
        result["date_to"] = data["form"]["date_to"] or False
        result["strict_range"] = True if result["date_from"] else False
        result["company_id"] = data["form"]["company_id"][0] or False
        return result

    def _print_report(self, report_type):
        self.ensure_one()
        data = {
            "form": self.read(
                [
                    "account_report_id",
                    "date_from_cmp",
                    "date_to_cmp",
                    "journal_ids",
                    "filter_cmp",
                    "target_move",
                    "enable_filter",
                    "debit_credit",
                    "date_from",
                    "date_to",
                    "company_id",
                    "show_analytic_account",
                    "analytic_account_ids",
                ]
            )[0]
        }
        used_context = self._build_contexts(data)
        data["form"]["used_context"] = dict(
            used_context, lang=get_lang(self.env).code)
        comparison_context = self._build_comparison_context(data)
        data["form"]["comparison_context"] = comparison_context

        if report_type == "xlsx":
            report_name = "a_b_s.report_financial_xlsx"
        else:
            report_name = "account_balance_sheet_report.report_financial"

        report = self.env["ir.actions.report"].search(
            [("report_name", "=", report_name),
             ("report_type", "=", report_type)],
            limit=1,
        )

        if not report:
            raise ValidationError(_("Report not found: %s") % report_name)

        return report.with_context(lang=self.env.lang).report_action(self, data=data)

    def button_export_pdf(self):
        self.ensure_one()
        report_type = "qweb-pdf"
        return self._export(report_type)

    def button_export_xlsx(self):
        self.ensure_one()
        report_type = "xlsx"
        return self._export(report_type)

    def _export(self, report_type):
        """Default export is PDF."""
        return self._print_report(report_type)
