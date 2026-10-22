from odoo import _, models, fields, api
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_open_discount_wizard(self):
        raise UserError(_(
            "Bulk discounts are not allowed. Apply a discount on each order line."
        ))

    amount_before_discount = fields.Monetary(
        string="Amount Before Discount",
        compute="_compute_discount_totals",
        store=True,
        currency_field="currency_id",
    )
    total_discount_amount = fields.Monetary(
        string="Total Discount Amount",
        compute="_compute_discount_totals",
        store=True,
        currency_field="currency_id",
    )
    total_discount_percent = fields.Float(
        string="Discount (%)",
        digits=(16, 2),
        compute="_compute_discount_totals",
        store=True,
    )

    last_invoice_date = fields.Date(
        string="Invoice Date",
        compute="_compute_last_invoice_date",
        store=True,
        help="Date of the latest posted customer invoice of this order.",
    )

    @api.depends("invoice_ids.state", "invoice_ids.invoice_date")
    def _compute_last_invoice_date(self):
        for order in self:
            invoices = order.invoice_ids.filtered(
                lambda move: move.state == "posted"
                             and move.move_type == "out_invoice"
                             and move.invoice_date
            )
            order.last_invoice_date = max(
                invoices.mapped("invoice_date"), default=False
            )

    @api.depends(
        "order_line.price_unit",
        "order_line.product_uom_qty",
        "order_line.discount_amount",
        "order_line.display_type",
    )
    def _compute_discount_totals(self):
        for order in self:
            lines = order.order_line.filtered(lambda line: not line.display_type)
            gross = sum(line.price_unit * line.product_uom_qty for line in lines)
            discount = sum(lines.mapped("discount_amount"))
            order.amount_before_discount = gross
            order.total_discount_amount = discount
            order.total_discount_percent = discount / gross * 100 if gross else 0.0
