import logging

from odoo import models

_logger = logging.getLogger(__name__)


class CarCheckout(models.Model):
    _inherit = "car.checkout"

    def _create_invoice_from_sale_order(self):
        """Invoice the main SO, then Contract upsell SOs to the car owner."""
        super()._create_invoice_from_sale_order()
        for checkout in self:
            checkout._create_invoices_for_contract_upsells()

    def _create_invoices_for_contract_upsells(self):
        """
        Create and post invoices for confirmed extra sale orders linked to a
        Contract order. Each extra keeps its own partner_id (sub-customer).
        Intern/Extern checkouts are untouched.
        """
        self.ensure_one()
        sale_order = self.sale_order_id
        if not sale_order or sale_order.order_type != "contract":
            return

        extras = sale_order.child_sale_ids.filtered(
            lambda order: order.state in ("sale", "done")
        )
        for extra in extras:
            self._invoice_sale_order_if_needed(extra)

    def _invoice_sale_order_if_needed(self, sale_order):
        """Create and post an invoice for a sale order when none exists yet."""
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
                "Failed to create invoice for contract upsell sale order %s",
                sale_order.name,
            )
