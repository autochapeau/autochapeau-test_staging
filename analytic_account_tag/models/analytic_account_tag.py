from odoo import models, fields


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    tag_ids = fields.Many2many(
        'analytic.account.tag',
        'analytic_account_tag_rel',
        'analytic_account_id',
        'tag_id',
        string='Tags',
        help='Tags for analytic accounts.'
    )


class AnalyticAccountTag(models.Model):
    _name = 'analytic.account.tag'
    _description = 'Analytic Account Tag'
    _order = 'name'

    name = fields.Char(string='Tags', required=True, translate=True)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(default=True)
