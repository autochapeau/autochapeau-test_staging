from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, ValidationError


PROFIT_LOSS_REPORT = "account_balance_sheet_report.account_financial_report_profitandloss0"
ACCOUNT_TYPES = {
    "income": "revenue",
    "expense_direct_cost": "costs",
    "expense": "operating_expenses",
    "income_other": "other_income",
    "expense_depreciation": "other_expenses",
}
EXPENSE_SECTIONS = {"costs", "operating_expenses", "other_expenses"}
TOTAL_SECTIONS = {
    "gross_profit": ("revenue", "costs"),
    "operating_income": ("gross_profit", "operating_expenses"),
    "net_profit": ("operating_income", "other_income", "other_expenses"),
}


class ProfitLossLayout(models.Model):
    _name = "account.profit.loss.layout"
    _description = "Profit and Loss Layout"
    _order = "name, id"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    line_ids = fields.One2many(
        "account.profit.loss.layout.line", "layout_id", copy=True,
        default=lambda self: [Command.create(line) for line in self._default_lines()],
    )

    @api.model
    def _sections(self):
        return [
            ("revenue", _("Revenue")),
            ("costs", _("Less Costs of Revenue")),
            ("gross_profit", _("Gross Profit")),
            ("operating_expenses", _("Less Operating Expenses")),
            ("operating_income", _("Operating Income (or Loss)")),
            ("other_income", _("Plus Other Income")),
            ("other_expenses", _("Less Other Expenses")),
            ("net_profit", _("Net Profit")),
        ]

    @api.model
    def _default_lines(self):
        return [
            {"section": section, "name": name, "sequence": sequence * 10}
            for sequence, (section, name) in enumerate(self._sections(), 1)
        ]

    def _report_lines(self):
        if not self:
            return self._default_lines()
        self.ensure_one()
        lines = self.line_ids.sorted("sequence").read(["section", "name", "sequence"])
        configured = {line["section"] for line in lines}
        return lines + [line for line in self._default_lines() if line["section"] not in configured]


class ProfitLossLayoutLine(models.Model):
    _name = "account.profit.loss.layout.line"
    _description = "Profit and Loss Layout Line"
    _order = "sequence, id"

    layout_id = fields.Many2one("account.profit.loss.layout", required=True, ondelete="cascade")
    sequence = fields.Integer(required=True, default=10)
    section = fields.Selection(selection=lambda self: self.env["account.profit.loss.layout"]._sections(), required=True)
    name = fields.Char(required=True, translate=True)

    _sql_constraints = [
        ("layout_section_uniq", "unique(layout_id, section)", "Each section can appear once in a layout."),
    ]


class ProfitLossReport(models.AbstractModel):
    _name = "account.profit.loss.report"
    _description = "Profit and Loss Report Data"

    @api.model
    def _get_values(self, form):
        company = self.env["res.company"].browse(form["company_id"][0])
        if company not in self.env.companies:
            raise AccessError(_("You cannot run this report for this company."))
        comparison = form.get("enable_filter")
        dated_comparison = comparison and form.get("filter_cmp") == "filter_date"
        start, end = form.get("date_from_cmp"), form.get("date_to_cmp")
        if dated_comparison and not (start and end):
            raise ValidationError(_("Enter both dates for the comparison period."))
        periods = [(form.get("date_from"), form.get("date_to"))]
        if dated_comparison:
            periods.append((start, end))
        if any(first and last and first > last for first, last in periods):
            raise ValidationError(_("The start date must be on or before the end date."))

        layout = self.env["account.profit.loss.layout"]
        if form.get("profit_loss_layout_id"):
            layout = layout.browse(form["profit_loss_layout_id"][0])
            if layout.company_id != company:
                raise ValidationError(_("Choose a layout for the report company."))
        domain = [
            ("company_id", "=", company.id),
            ("account_id.account_type", "in", list(ACCOUNT_TYPES)),
            ("parent_state", "in", ["draft", "posted"] if form.get("target_move") == "all" else ["posted"]),
        ]
        if form.get("journal_ids"):
            domain.append(("journal_id", "in", form["journal_ids"]))
        if form.get("show_analytic_account"):
            analytic_ids = self.env["account.analytic.account"].search(
                [("id", "in", form["analytic_account_ids"])] if form.get("analytic_account_ids") else []
            ).ids
            domain.append(("analytic_distribution_search", "in", analytic_ids))

        debit_credit = form.get("debit_credit") and not comparison
        balances = self._balances(domain, form.get("date_from"), form.get("date_to"))
        compared = {}
        if comparison:
            compared = self._balances(domain, start, end) if dated_comparison else self._balances(domain, False, False)

        columns = [("balance", _("Balance"))]
        if comparison:
            columns.append(("comparison", form.get("label_filter") or _("Comparison")))
        elif debit_credit:
            columns = [("debit", _("Debit")), ("credit", _("Credit"))] + columns
        return {
            "form": form, "company": company, "columns": columns,
            "rows": self._rows(layout, balances, compared, form.get("profit_loss_details")),
        }

    @api.model
    def _balances(self, domain, date_from, date_to):
        period = list(domain)
        if date_from:
            period.append(("date", ">=", date_from))
        if date_to:
            period.append(("date", "<=", date_to))
        return {
            account: (debit, credit)
            for account, debit, credit in self.env["account.move.line"]._read_group(
                period, ["account_id"], ["debit:sum", "credit:sum"],
            )
        }

    @api.model
    def _rows(self, layout, balances, compared, include_details):
        measures = ("balance", "comparison", "debit", "credit")
        amounts = {section: dict.fromkeys(measures, 0.0) for section in ACCOUNT_TYPES.values()}
        details = {section: [] for section in amounts}
        accounts = balances.keys() | compared.keys()
        for account in sorted(accounts, key=lambda account: (account.code, account.id)):
            section = ACCOUNT_TYPES[account.account_type]
            debit, credit = balances.get(account, (0, 0))
            past_debit, past_credit = compared.get(account, (0, 0))
            sign = 1 if section in EXPENSE_SECTIONS else -1
            row = {"balance": sign * (debit - credit), "comparison": sign * (past_debit - past_credit),
                   "debit": debit, "credit": credit}
            for measure in measures:
                amounts[section][measure] += row[measure]
            if include_details and any(row.values()):
                details[section].append(dict(row, name=account.display_name, detail=True))

        for section, parts in TOTAL_SECTIONS.items():
            amounts[section] = {
                measure: sum(amounts[part][measure] * (-1 if part in EXPENSE_SECTIONS and measure in ("balance", "comparison") else 1)
                             for part in parts)
                for measure in measures
            }
        rows = []
        for line in layout._report_lines():
            section = line["section"]
            rows.append(dict(amounts[section], name=line["name"], total=section in TOTAL_SECTIONS))
            rows.extend(details.get(section, []))
        return rows
