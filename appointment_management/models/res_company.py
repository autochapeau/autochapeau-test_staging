from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    branch_code = fields.Char()
    loyalty_program_id = fields.Many2one("loyalty.program")
    wallet_program_id = fields.Many2one("loyalty.program")
