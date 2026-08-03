from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        result = super().action_post()
        sale_orders = self.filtered(
            lambda move: move.move_type == "out_invoice"
        ).invoice_line_ids.sale_line_ids.order_id
        sale_orders.mapped("split_payment_ids").filtered(
            lambda payment: payment.state == "paid"
            and payment.account_payment_id
        )._reconcile_available_invoices()
        return result
