import logging

from odoo import models

_logger = logging.getLogger(__name__)


class CarCheckout(models.Model):
    _inherit = "car.checkout"

    def _create_invoice_from_sale_order(self):
        """Invoice the main Extern SO, then its upsell SO (same car owner)."""
        super()._create_invoice_from_sale_order()
        for checkout in self:
            checkout._create_invoices_for_extern_upsells()

    def _create_invoices_for_extern_upsells(self):
        """
        Create invoices for confirmed extra sale orders linked to an Extern
        order. Both parent and extra invoice the car owner. Referral commission
        is generated only from the parent Extern order.
        """
        self.ensure_one()
        sale_order = self.sale_order_id
        if not sale_order or sale_order.order_type != "extern":
            return

        extras = sale_order.child_sale_ids.filtered(
            lambda order: order.state in ("sale", "done")
        )
        for extra in extras:
            self._invoice_extern_sale_order_if_needed(extra)

    def _invoice_extern_sale_order_if_needed(self, sale_order):
        self.ensure_one()
        if not sale_order:
            return

        existing_invoices = self.env["account.move"].search([
            ("invoice_origin", "=", sale_order.name),
            ("move_type", "in", ["out_invoice", "out_refund"]),
            ("state", "!=", "cancel"),
        ])
        if existing_invoices:
            return

        try:
            invoices = sale_order._create_invoices()
            for invoice in invoices:
                if invoice.state == "draft":
                    invoice.action_post()
        except Exception:
            _logger.exception(
                "Failed to create invoice for extern upsell sale order %s",
                sale_order.name,
            )
