from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        self.order_line._check_user_discount_limit()
        return super().action_confirm()
