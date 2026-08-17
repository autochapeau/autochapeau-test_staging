from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    split_payment_ids = fields.One2many(
        "sale.order.payment",
        "sale_order_id",
        string="Payments",
        copy=False,
    )
    split_payment_count = fields.Integer(
        compute="_compute_split_payment_totals",
    )
    split_amount_paid = fields.Monetary(
        string="Paid",
        compute="_compute_split_payment_totals",
        currency_field="currency_id",
    )
    split_amount_pending = fields.Monetary(
        string="Pending",
        compute="_compute_split_payment_totals",
        currency_field="currency_id",
    )
    split_amount_remaining = fields.Monetary(
        string="Remaining",
        compute="_compute_split_payment_totals",
        currency_field="currency_id",
    )

    @api.depends(
        "amount_total",
        "split_payment_ids.amount",
        "split_payment_ids.state",
    )
    def _compute_split_payment_totals(self):
        for order in self:
            active_payments = order.split_payment_ids.filtered(
                lambda payment: payment.state != "cancelled"
            )
            paid = sum(
                active_payments.filtered(
                    lambda payment: payment.state == "paid"
                ).mapped("amount")
            )
            pending = sum(
                active_payments.filtered(
                    lambda payment: payment.state in ("processing", "pending", "needs_review")
                ).mapped("amount")
            )
            order.split_payment_count = len(active_payments)
            order.split_amount_paid = paid
            order.split_amount_pending = pending
            order.split_amount_remaining = max(order.amount_total - paid - pending, 0.0)

    def action_open_split_payment_wizard(self):
        self.ensure_one()
        if not self.id:
            raise UserError(_("Please save the sale order first."))
        if self.state == "cancel":
            raise UserError(_("Payments cannot be collected for a cancelled sale order."))
        if self.currency_id.is_zero(self.split_amount_remaining):
            raise UserError(_("This sale order has no remaining amount to collect."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Collect Payment"),
            "res_model": "sale.split.payment.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_sale_order_id": self.id,
            },
        }

    def action_open_multi_split_payment_wizard(self):
        orders = self.exists()
        if not orders:
            raise UserError(_("Please select at least one sale order."))
        invalid_orders = orders.filtered(
            lambda order: order.state not in ("sale", "done")
            or order.currency_id.is_zero(order.split_amount_remaining)
        )
        if invalid_orders:
            raise UserError(
                _(
                    "Only confirmed sale orders with a remaining amount can be selected."
                )
            )
        if len(orders.mapped("partner_id")) != 1:
            raise UserError(_("All selected sale orders must belong to the same customer."))
        if len(orders.mapped("company_id")) != 1:
            raise UserError(_("All selected sale orders must belong to the same company."))
        if len(orders.mapped("currency_id")) != 1:
            raise UserError(_("All selected sale orders must use the same currency."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Collect Payment for Multiple Orders"),
            "res_model": "sale.multi.split.payment.wizard",
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "sale_split_payment.view_sale_multi_split_payment_wizard_form"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
            "context": {
                "default_sale_order_ids": [(6, 0, orders.ids)],
            },
        }

    def action_view_split_payments(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sale_split_payment.action_sale_order_payment"
        )
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {
            "default_sale_order_id": self.id,
            "search_default_not_cancelled": 1,
        }
        return action

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super()._create_invoices(
            grouped=grouped,
            final=final,
            date=date,
        )
        self.mapped("split_payment_ids").filtered(
            lambda payment: payment.state == "paid" and payment.account_payment_id
        )._reconcile_available_invoices()
        return invoices
