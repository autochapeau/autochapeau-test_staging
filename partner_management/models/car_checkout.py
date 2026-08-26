from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CarCheckout(models.Model):
    _inherit = "car.checkout"

    sale_order_state = fields.Selection(
        related="sale_order_id.state",
        string="Sale Order Status",
    )
    sale_currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
    )
    sale_split_amount_remaining = fields.Monetary(
        related="sale_order_id.split_amount_remaining",
        currency_field="sale_currency_id",
        string="Remaining to Collect",
    )
    sale_split_amount_paid = fields.Monetary(
        related="sale_order_id.split_amount_paid",
        currency_field="sale_currency_id",
        string="Sale Order Paid",
    )
    sale_amount_total = fields.Monetary(
        related="sale_order_id.amount_total",
        currency_field="sale_currency_id",
        string="Sale Order Total",
    )
    sale_has_service_product_lines = fields.Boolean(
        related="sale_order_id.has_service_product_lines",
    )
    sale_order_type = fields.Selection(
        related="sale_order_id.order_type",
        string="Sale Order Type",
    )
    sale_order_is_fully_paid = fields.Boolean(
        string="Sale Order Fully Paid",
        compute="_compute_sale_order_is_fully_paid",
    )

    def _get_payment_sale_orders(self):
        """Sale orders whose payment gates checkout approval."""
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return self.env["sale.order"]
        if order.order_type == "contract":
            # Contract is invoiced to the dealer monthly; only extras are
            # collected at the branch before checkout approval.
            return order.child_sale_ids.filtered(
                lambda sale: sale.state in ("sale", "done")
            )
        return order

    def _is_sale_order_fully_paid(self, order):
        return order.currency_id.compare_amounts(
            order.split_amount_paid,
            order.amount_total,
        ) >= 0

    @api.depends(
        "sale_order_id",
        "sale_order_id.order_type",
        "sale_order_id.split_amount_paid",
        "sale_order_id.amount_total",
        "sale_order_id.currency_id",
        "sale_order_id.child_sale_ids",
        "sale_order_id.child_sale_ids.state",
        "sale_order_id.child_sale_ids.split_amount_paid",
        "sale_order_id.child_sale_ids.amount_total",
        "sale_order_id.child_sale_ids.currency_id",
    )
    def _compute_sale_order_is_fully_paid(self):
        for checkout in self:
            orders = checkout._get_payment_sale_orders()
            if not orders:
                linked = checkout.sale_order_id
                checkout.sale_order_is_fully_paid = bool(
                    linked and linked.order_type == "contract"
                )
                continue
            checkout.sale_order_is_fully_paid = all(
                checkout._is_sale_order_fully_paid(order)
                for order in orders
            )

    def action_view_sale_order(self):
        """Open the sale order linked to this checkout."""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("No sale order is linked to this checkout."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Sale Order"),
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_open_split_payment_wizard(self):
        """Collect payment on the linked sale order."""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_(
                "Collect Payment requires a sale order linked to this checkout."
            ))
        if self.sale_order_id.order_type == "contract":
            raise UserError(_(
                "Contract sale orders are billed to the dealer monthly. "
                "Collect payment on the extra sale orders instead."
            ))
        return self.sale_order_id.action_open_split_payment_wizard()

    def action_progress(self):
        self.ensure_one()
        if self.sale_order_id and not self.sale_order_is_fully_paid:
            unpaid = self._get_payment_sale_orders().filtered(
                lambda order: not self._is_sale_order_fully_paid(order)
            )
            details = "\n".join(
                _(
                    "%(name)s: paid %(paid)s / %(total)s",
                    name=order.name,
                    paid=order.split_amount_paid,
                    total=order.amount_total,
                )
                for order in unpaid
            )
            if self.sale_order_id.order_type == "contract":
                raise UserError(_(
                    "Request approval is only available after all extra "
                    "sale orders are fully paid:\n%(details)s",
                    details=details,
                ))
            raise UserError(_(
                "Request approval is only available after the linked sale order "
                "is fully paid.\nPaid: %(paid)s / %(total)s",
                paid=self.sale_split_amount_paid,
                total=self.sale_amount_total,
            ))
        return super().action_progress()
