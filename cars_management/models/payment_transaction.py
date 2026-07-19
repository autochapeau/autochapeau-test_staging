from odoo import fields, models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    donation_amount = fields.Float(readonly=True)
    donation_move_id = fields.Many2one("account.move", "Donation Journal Entry", readonly=True, check_company=True)
    wallet_amount = fields.Float(readonly=True)
