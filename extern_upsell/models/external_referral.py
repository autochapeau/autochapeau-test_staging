from odoo import _, api, models


class ExternalReferral(models.Model):
    _inherit = "external.referral"

    @api.model
    def _sync_paid_invoices(self, invoices):
        """
        Create referral lines only for parent Extern orders.

        Extra/upsell orders linked via related_sale_id never generate commission,
        even if their type were mistakenly set to extern.
        """
        for invoice in invoices.filtered(
            lambda move: (
                move.move_type == "out_invoice"
                and move.state == "posted"
                and move.payment_state in ("paid", "in_payment")
            )
        ):
            orders = invoice.invoice_line_ids.sale_line_ids.order_id.filtered(
                lambda order: (
                    order.order_type == "extern"
                    and not order.related_sale_id
                    and order.agency_id
                    and order.agency_salesperson_id
                    and order.external_referral_percent > 0
                )
            )
            for order in orders:
                invoice_lines = invoice.invoice_line_ids.filtered(
                    lambda line: (
                        line.display_type == "product"
                        and order in line.sale_line_ids.order_id
                    )
                )
                base_amount = sum(invoice_lines.mapped("price_subtotal"))
                if invoice.currency_id.is_zero(base_amount):
                    continue
                amount = invoice.currency_id.round(
                    base_amount * order.external_referral_percent / 100
                )
                values = {
                    "name": _(
                        "%(invoice)s - %(salesperson)s",
                        invoice=invoice.name,
                        salesperson=order.agency_salesperson_id.display_name,
                    ),
                    "agency_id": order.agency_id.id,
                    "agency_salesperson_id": order.agency_salesperson_id.id,
                    "sale_order_id": order.id,
                    "invoice_id": invoice.id,
                    "company_id": invoice.company_id.id,
                    "currency_id": invoice.currency_id.id,
                    "base_amount": base_amount,
                    "referral_percent": order.external_referral_percent,
                    "amount": amount,
                    "state": "due",
                    "paid_date": False,
                }
                referral = self.search([
                    ("invoice_id", "=", invoice.id),
                    ("sale_order_id", "=", order.id),
                ], limit=1)
                if not referral:
                    self.create(values)
                elif referral.state != "paid":
                    referral.write(values)
