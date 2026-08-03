from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ExternalReferral(models.Model):
    _name = "external.referral"
    _description = "External Referral"
    _order = "invoice_date desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False)
    agency_id = fields.Many2one(
        "res.partner",
        string="Agency",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    agency_salesperson_id = fields.Many2one(
        "res.partner",
        string="Agency Salesperson",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    invoice_id = fields.Many2one(
        "account.move",
        required=True,
        readonly=True,
        ondelete="restrict",
        domain="[('move_type', '=', 'out_invoice')]",
    )
    invoice_date = fields.Date(
        related="invoice_id.invoice_date",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        readonly=True,
    )
    base_amount = fields.Monetary(
        string="Untaxed Base",
        currency_field="currency_id",
        required=True,
        readonly=True,
    )
    referral_percent = fields.Float(
        string="Referral (%)",
        digits=(5, 2),
        required=True,
        readonly=True,
    )
    amount = fields.Monetary(
        string="Referral Amount",
        currency_field="currency_id",
        required=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("due", "Due"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="due",
        readonly=True,
    )
    paid_date = fields.Date(readonly=True, copy=False)
    payment_reference = fields.Char(copy=False)
    note = fields.Text()

    _sql_constraints = [
        (
            "invoice_sale_order_unique",
            "unique(invoice_id, sale_order_id)",
            "An external referral already exists for this invoice and sale order.",
        ),
    ]

    @api.model
    def _sync_paid_invoices(self, invoices):
        """Create one due referral once the customer's payment is registered."""
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

    @api.model
    def _cancel_open_for_invoices(self, invoices):
        referrals = self.search([
            ("invoice_id", "in", invoices.ids),
            ("state", "=", "due"),
        ])
        referrals.write({"state": "cancelled"})

    def action_generate_referrals(self):
        invoices = self.env["account.move"].search([
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("paid", "in_payment")),
            ("invoice_line_ids.sale_line_ids.order_id.order_type", "=", "extern"),
        ])
        before_count = self.search_count([])
        self._sync_paid_invoices(invoices)
        created_count = self.search_count([]) - before_count
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("External Referrals"),
                "message": _(
                    "%(created)s referral(s) generated from "
                    "%(invoices)s eligible paid invoice(s).",
                    created=created_count,
                    invoices=len(invoices),
                ),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "soft_reload",
                },
            },
        }

    def action_mark_paid(self):
        for referral in self:
            if referral.state != "due":
                raise UserError(_(
                    "Only due referrals can be marked as paid."
                ))
        self.write({
            "state": "paid",
            "paid_date": fields.Date.context_today(self),
        })
        return True

    def action_reset_to_due(self):
        self.write({
            "state": "due",
            "paid_date": False,
        })
        return True
