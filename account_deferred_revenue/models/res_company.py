from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    deferred_revenue_journal_id = fields.Many2one(
        "account.journal",
        string="Deferred Revenue Journal",
        domain="[('type', '=', 'general')]",
        check_company=True,
    )
    deferred_revenue_account_id = fields.Many2one(
        "account.account",
        string="Deferred Revenue Account",
        domain="[('deprecated', '=', False), ('account_type', 'in', ('liability_current', 'liability_non_current'))]",
        check_company=True,
        help="Liability account used until revenue is recognized.",
    )
    deferred_expense_account_id = fields.Many2one(
        "account.account",
        string="Deferred Expense Account",
        domain="[('deprecated', '=', False), ('account_type', 'in', ('asset_current', 'asset_non_current', 'asset_prepayments'))]",
        check_company=True,
        help="Prepaid/asset account used until expense is recognized.",
    )
