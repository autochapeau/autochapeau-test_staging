from odoo import _, api, models


class ExternalReferral(models.Model):
    _inherit = "external.referral"

    def _eligible_orders_for_invoice(self, invoice):
        """Parent Extern orders only (extra/upsell never generate commission)."""
        return invoice.invoice_line_ids.sale_line_ids.order_id.filtered(
            lambda order: (
                order.order_type == "extern"
                and not order.related_sale_id
                and order.agency_id
                and order.agency_salesperson_id
                and self._order_has_manual_commissions(order)
            )
        )
