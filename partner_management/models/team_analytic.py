from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SalesTeam(models.Model):
    _inherit = "crm.team"

    sales_analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Sales Analytic Account", check_company=True,
        domain="[('company_id', 'in', [False, company_id]), ('active', '=', True)]",
    )

    def _merge_team_analytic_distribution(self, distribution, company, previous_auto=False):
        if self:
            self.ensure_one()
        result = dict(distribution or {})
        account = self.sales_analytic_account_id
        if account and (not account.active or (account.company_id and account.company_id != company)):
            raise ValidationError(_("The sales team's analytic account must be active and belong to the order's company."))
        accounts = self.env["account.analytic.account"].browse([
            int(ident) for key in result for ident in key.split(",") if ident
        ]).exists()
        # Replace a previously generated default only if the entire old plan is
        # still the untouched, 100% default. User allocations remain protected.
        if previous_auto:
            old_plan_accounts = accounts.filtered(lambda a: a.root_plan_id == previous_auto.root_plan_id)
            old_percent = sum(percent for key, percent in result.items() if str(previous_auto.id) in key.split(","))
            if old_plan_accounts == previous_auto and old_percent == 100:
                cleaned = {}
                for key, percent in result.items():
                    remaining = ",".join(ident for ident in key.split(",") if ident != str(previous_auto.id))
                    if remaining:
                        cleaned[remaining] = cleaned.get(remaining, 0) + percent
                result = cleaned
                accounts -= previous_auto
        if not account:
            return result, False
        if accounts.filtered(lambda a: a.root_plan_id == account.root_plan_id):
            return result, False
        result[str(account.id)] = 100.0
        return result, True


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    sales_team_analytic_account_id = fields.Many2one(
        "account.analytic.account", readonly=True, copy=False,
    )

    @api.depends("order_id.partner_id", "product_id", "order_id.team_id",
                 "order_id.team_id.sales_analytic_account_id")
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for line in self.filtered(lambda item: not item.display_type):
            distribution, generated = line.order_id.team_id._merge_team_analytic_distribution(
                line.analytic_distribution, line.company_id, line.sales_team_analytic_account_id,
            )
            line.analytic_distribution = distribution
            line.sales_team_analytic_account_id = line.order_id.team_id.sales_analytic_account_id if generated else False


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_prepare_team_analytic_backfill(self):
        if not self.env.su and not self.env.user.has_group("sales_team.group_sale_manager"):
            raise AccessError(_("Only sales managers can update historical sales analytics."))
        self.check_access_rights("write")
        self.check_access_rule("write")
        wizard = self.env["team.analytic.backfill"].create({"sale_order_ids": [(6, 0, self.ids)]})
        return wizard._open_preview()


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_prepare_team_analytic_backfill(self):
        if not self.env.su and not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(_("Only accounting managers can update historical invoice analytics."))
        self.check_access_rights("write")
        self.check_access_rule("write")
        wizard = self.env["team.analytic.backfill"].create({"move_ids": [(6, 0, self.ids)]})
        return wizard._open_preview()
