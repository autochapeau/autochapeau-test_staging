import time

from odoo import _, api, models
from odoo.exceptions import UserError


class ReportFinancial(models.AbstractModel):
    _name = "report.account_balance_sheet_report.report_financial"
    _description = "Report Account Balance Sheet"

    def _compute_account_balance(self, accounts, analytic_ids=None):
        """Compute the balance, debit, and credit for the provided accounts"""
        mapping = {
            "balance": "COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance",
            "debit": "COALESCE(SUM(debit), 0) as debit",
            "credit": "COALESCE(SUM(credit), 0) as credit",
        }

        res = {account.id: dict.fromkeys(mapping, 0.0) for account in accounts}

        if accounts:
            # Get the new query method in Odoo 17
            domain = []
            query = self.env["account.move.line"]._where_calc(domain)
            self.env["account.move.line"]._apply_ir_rules(query, "read")
            tables, where_clause, where_params = query.get_sql()

            tables = tables.replace('"', "") if tables else "account_move_line"
            wheres = [""]
            if where_clause.strip():
                wheres.append(where_clause.strip())

            # Ajouter le filtre analytique si spécifié
            if analytic_ids:
                # Filter by analytic_distribution JSON
                # Les clés dans JSON sont des strings
                analytic_conditions = " OR ".join(
                    [f"analytic_distribution::jsonb ? '{str(aid)}'" for aid in analytic_ids]
                )
                wheres.append(f"({analytic_conditions})")

            filters = " AND ".join(wheres)

            request = (
                "SELECT account_id as id, "
                + ", ".join(mapping.values())
                + " FROM "
                + tables
                + " WHERE account_id IN %s "
                + filters
                + " GROUP BY account_id"
            )
            params = (tuple(accounts._ids),) + tuple(where_params)
            self.env.cr.execute(request, params)

            for row in self.env.cr.dictfetchall():
                res[row["id"]] = row

        return res

    def _compute_report_balance(self, reports, analytic_ids=None):
        """returns a dictionary with key=the ID of a record and value=the credit,
        debit and balance amount
        computed for this record. If the record is of type :
        'accounts' : it's the sum of the linked accounts
        'account_type' : it's the sum of leaf accoutns with such an account_type
        'account_report' : it's the amount of the related report
        'sum' : it's the sum of the children of this record (aka a 'view' record)"""
        res = {}
        fields = ["credit", "debit", "balance"]
        for report in reports:
            if report.id in res:
                continue
            res[report.id] = {fn: 0.0 for fn in fields}
            if report.type == "accounts":
                # it's the sum of the linked accounts
                res[report.id]["account"] = self._compute_account_balance(
                    report.account_ids, analytic_ids=analytic_ids)
                for value in res[report.id]["account"].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == "account_type":
                # it's the sum the leaf accounts with such an account type
                account_type = report.account_type_ids.mapped("type")
                accounts = self.env["account.account"].search(
                    [("account_type", "in", account_type)])
                res[report.id]["account"] = self._compute_account_balance(
                    accounts, analytic_ids=analytic_ids)
                for value in res[report.id]["account"].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == "account_report" and report.account_report_id:
                # it's the amount of the linked report
                res2 = self._compute_report_balance(
                    report.account_report_id, analytic_ids=analytic_ids)
                for _key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
            elif report.type == "sum":
                # it's the sum of the children of this account.report
                res2 = self._compute_report_balance(
                    report.children_ids, analytic_ids=analytic_ids)
                for _key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
        return res

    # flake8: noqa: C901
    def get_account_lines(self, data):
        # Si filtre analytique actif, grouper par analytic
        form_data = data.get("form", {})
        analytic_ids = form_data.get("analytic_account_ids")
        show_analytic = form_data.get("show_analytic_account", False)

        if show_analytic:
            # Si le filtre analytique est activé
            if not analytic_ids:
                # Si aucun n'est sélectionné, charger TOUS les comptes analytiques
                analytic_accounts = self.env['account.analytic.account'].search([
                ])
            else:
                # Si certains sont sélectionnés, utiliser ceux-ci
                analytic_accounts = self.env['account.analytic.account'].browse(
                    analytic_ids)

            analytic_blocks = []
            account_report = self.env["account.financial.report"].search(
                [("id", "=", form_data["account_report_id"][0])])
            child_reports = account_report.with_context(
                lang=self.env.user.lang)._get_children_by_order()

            # Variables pour le total général
            grand_total_income = 0.0
            grand_total_expense = 0.0
            grand_total_balance = 0.0

            for analytic in analytic_accounts:
                # Appliquer le filtre analytique
                res = self._compute_report_balance(
                    child_reports, analytic_ids=[analytic.id])
                lines = []
                analytic_income_total = 0.0
                analytic_expense_total = 0.0

                for report in child_reports:
                    vals = {
                        "name": _(report.name),
                        "balance": res[report.id]["balance"] * float(report.sign),
                        "type": "report",
                        "level": bool(report.style_overwrite) and report.style_overwrite or report.level,
                        "account_type": report.type or False,
                    }

                    if form_data.get("debit_credit"):
                        vals["debit"] = res[report.id]["debit"]
                        vals["credit"] = res[report.id]["credit"]

                    # Accumule les totaux par analytique
                    report_name = report.name.lower()
                    if 'income' in report_name:
                        analytic_income_total += vals["balance"]
                    elif 'expense' in report_name:
                        analytic_expense_total += vals["balance"]

                    lines.append(vals)
                    if report.display_detail == "no_detail":
                        continue
                    if res[report.id].get("account"):
                        sub_lines = []
                        for account_id, value in res[report.id]["account"].items():
                            flag = False
                            account = self.env["account.account"].browse(
                                account_id)
                            vals = {
                                "name": account.code + " " + account.name,
                                "balance": value["balance"] * float(report.sign) or 0.0,
                                "type": "account",
                                "level": report.display_detail == "detail_with_hierarchy" and 4,
                                "account_type": account.account_type,
                            }
                            if form_data.get("debit_credit"):
                                vals["debit"] = value["debit"]
                                vals["credit"] = value["credit"]
                                if not account.company_id.currency_id.is_zero(vals["debit"]) or not account.company_id.currency_id.is_zero(vals["credit"]):
                                    flag = True
                            if not account.company_id.currency_id.is_zero(vals["balance"]):
                                flag = True
                            if flag:
                                sub_lines.append(vals)
                        lines += sorted(sub_lines,
                                        key=lambda sub_line: sub_line["name"])

                analytic_balance_total = analytic_income_total + analytic_expense_total

                # Accumule les totaux généraux
                grand_total_income += analytic_income_total
                grand_total_expense += analytic_expense_total
                grand_total_balance += analytic_balance_total

                analytic_blocks.append({
                    'analytic': analytic.name,
                    'income_total': analytic_income_total,
                    'expense_total': analytic_expense_total,
                    'balance_total': analytic_balance_total,
                    'lines': lines
                })

            # Ajouter un bloc généralisé TOTAL
            analytic_blocks.append({
                'analytic': 'TOTAL',
                'income_total': grand_total_income,
                'expense_total': grand_total_expense,
                'balance_total': grand_total_balance,
                'lines': [],
                'is_total': True
            })

            return analytic_blocks

        # Sinon, comportement standard
        lines = []
        account_report = self.env["account.financial.report"].search(
            [("id", "=", form_data["account_report_id"][0])])
        child_reports = account_report.with_context(
            lang=self.env.user.lang)._get_children_by_order()
        res = self._compute_report_balance(child_reports)
        if form_data.get("enable_filter"):
            comparison_res = self._compute_report_balance(child_reports)
            for report_id, value in comparison_res.items():
                res[report_id]["comp_bal"] = value["balance"]
                report_acc = res[report_id].get("account")
                if report_acc:
                    for account_id, val in comparison_res[report_id].get("account").items():
                        report_acc[account_id]["comp_bal"] = val["balance"]
        for report in child_reports:
            vals = {
                "name": _(report.name),
                "balance": res[report.id]["balance"] * float(report.sign),
                "type": "report",
                "level": bool(report.style_overwrite) and report.style_overwrite or report.level,
                # used to underline the financial report balances
                "account_type": report.type or False,
            }
            if form_data.get("debit_credit"):
                vals["debit"] = res[report.id]["debit"]
                vals["credit"] = res[report.id]["credit"]

            if form_data.get("enable_filter"):
                vals["balance_cmp"] = res[report.id]["comp_bal"] * \
                    float(report.sign)

            lines.append(vals)
            if report.display_detail == "no_detail":
                # the rest of the loop is used to display the details of the financial report,
                # so it's not needed here.
                continue
            if res[report.id].get("account"):
                sub_lines = []
                for account_id, value in res[report.id]["account"].items():
                    # if there are accounts to display, we add them to the lines with
                    # a level equals to their level in
                    # the COA + 1 (to avoid having them with a too low level that would
                    # conflicts with the level of data
                    # financial reports for Assets, liabilities...)
                    flag = False
                    account = self.env["account.account"].browse(account_id)
                    vals = {
                        "name": account.code + " " + account.name,
                        "balance": value["balance"] * float(report.sign) or 0.0,
                        "type": "account",
                        "level": report.display_detail == "detail_with_hierarchy" and 4,
                        "account_type": account.account_type,
                    }
                    if form_data.get("debit_credit"):
                        vals["debit"] = value["debit"]
                        vals["credit"] = value["credit"]
                        if not account.company_id.currency_id.is_zero(
                            vals["debit"]
                        ) or not account.company_id.currency_id.is_zero(vals["credit"]):
                            flag = True
                    if not account.company_id.currency_id.is_zero(vals["balance"]):
                        flag = True
                    if form_data.get("enable_filter"):
                        vals["balance_cmp"] = value["comp_bal"] * \
                            float(report.sign)
                        if not account.company_id.currency_id.is_zero(vals["balance_cmp"]):
                            flag = True
                    if flag:
                        sub_lines.append(vals)
                lines += sorted(sub_lines,
                                key=lambda sub_line: sub_line["name"])
        return lines

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get("form") or not self.env.context.get("active_model") or not self.env.context.get("active_id"):
            raise UserError(
                _("Form content is missing, this report cannot be printed."))
        model = self.env.context.get("active_model")
        docs = self.env[model].browse(self.env.context.get("active_id"))
        report_lines = self.get_account_lines(data)
        return {
            "doc_ids": self.ids,
            "doc_model": model,
            "data": data["form"],
            "docs": docs,
            "time": time,
            "get_account_lines": report_lines,
        }
