from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_open_discount_wizard(self):
        raise UserError(_(
            "Bulk discounts are not allowed. Apply a discount on each order line."
        ))
