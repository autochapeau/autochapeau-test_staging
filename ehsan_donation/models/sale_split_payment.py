from odoo import api, fields, models


class SaleSplitPaymentWizard(models.TransientModel):
    _inherit = "sale.split.payment.wizard"

    amount_total = fields.Monetary(
        string="Sale Order Cost",
        related="sale_order_id.amount_total",
        currency_field="currency_id",
        readonly=True,
    )
    ehsan_donation_amount = fields.Monetary(
        string="Ehsan Donation",
        related="sale_order_id.ehsan_donation_amount",
        currency_field="currency_id",
        readonly=True,
    )
    total_with_ehsan_donation = fields.Monetary(
        string="Total to Collect",
        compute="_compute_total_with_ehsan_donation",
        currency_field="currency_id",
        readonly=True,
    )

    @api.depends(
        "sale_order_id.amount_total",
        "sale_order_id.ehsan_donation_amount",
    )
    def _compute_total_with_ehsan_donation(self):
        for wizard in self:
            order = wizard.sale_order_id
            wizard.total_with_ehsan_donation = (
                order.amount_total + (order.ehsan_donation_amount or 0.0)
            )
