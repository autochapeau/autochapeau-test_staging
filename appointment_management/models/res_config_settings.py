from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    loyalty_program_id = fields.Many2one(
        "loyalty.program", string="Default Loyalty Program", related="company_id.loyalty_program_id", readonly=False
    )
    wallet_program_id = fields.Many2one(
        "loyalty.program", string="Default Wallet Program", related="company_id.wallet_program_id", readonly=False
    )
