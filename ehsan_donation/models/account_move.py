import logging

from odoo import _, api, fields, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    company_ehsan_donation_amount = fields.Monetary(
        string="Company Ehsan Donation",
        currency_field="currency_id",
        copy=False,
        readonly=True,
        help="Company donation generated when paid invoices of the related sale reach the threshold.",
    )
    company_ehsan_donation_move_id = fields.Many2one(
        "account.move",
        string="Company Ehsan Donation Journal Entry",
        copy=False,
        readonly=True,
        check_company=True,
    )
    company_ehsan_donation_state = fields.Selection(
        selection=[
            ("pending", "Pending Journal"),
            ("posted", "Posted"),
        ],
        string="Company Ehsan Donation Status",
        compute="_compute_company_ehsan_donation_state",
        store=True,
        copy=False,
    )

    @api.depends("company_ehsan_donation_amount", "company_ehsan_donation_move_id")
    def _compute_company_ehsan_donation_state(self):
        for move in self:
            if move.company_ehsan_donation_move_id:
                move.company_ehsan_donation_state = "posted"
            elif move.company_ehsan_donation_amount:
                move.company_ehsan_donation_state = "pending"
            else:
                move.company_ehsan_donation_state = False

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        self._post_ehsan_donations_on_paid()
        return res

    def write(self, vals):
        res = super().write(vals)
        # Backup: some payment flows update payment_state without _invoice_paid_hook.
        if vals.get("payment_state") in ("paid", "in_payment"):
            self.filtered(
                lambda move: move.move_type == "out_invoice"
                and move.payment_state in ("paid", "in_payment")
            )._post_ehsan_donations_on_paid()
        return res

    def _post_ehsan_donations_on_paid(self):
        """Post customer and company Ehsan donation entries on paid invoices."""
        paid_invoices = self.filtered(
            lambda move: move.move_type == "out_invoice"
            and move.payment_state in ("paid", "in_payment")
        )
        orders = paid_invoices.invoice_line_ids.sale_line_ids.order_id
        for order in orders:
            donation_invoice = paid_invoices.filtered(
                lambda invoice: any(
                    line.ehsan_donation_sale_order_id == order
                    for line in invoice.invoice_line_ids
                )
            )[:1]
            if donation_invoice:
                order.ehsan_donation_invoice_id = donation_invoice.id
            elif order.ehsan_donation_amount and not order.ehsan_donation_move_id:
                # Compatibility for invoices created before donation invoice lines existed.
                order._create_ehsan_donation_move()
        for invoice in paid_invoices:
            related_orders = invoice.invoice_line_ids.sale_line_ids.order_id
            if related_orders:
                for order in related_orders:
                    order._create_company_ehsan_donation_move(trigger_invoice=invoice)
            else:
                invoice._create_company_ehsan_donation_move()

    def _should_create_company_ehsan_donation(self):
        """Standalone invoices only. Sale-linked invoices are handled on the order."""
        self.ensure_one()
        company = self.company_id
        if not company.ehsan_company_donation_enabled:
            return False
        if self.move_type != "out_invoice":
            return False
        if self.payment_state not in ("paid", "in_payment"):
            return False
        if self.company_ehsan_donation_move_id:
            return False
        if self.invoice_line_ids.sale_line_ids.order_id:
            return False
        threshold = company.ehsan_company_donation_threshold or 0.0
        amount = company.ehsan_company_donation_amount or 0.0
        if float_compare(amount, 0.0, precision_rounding=self.currency_id.rounding) <= 0:
            return False
        return (
            float_compare(
                self.amount_untaxed,
                threshold,
                precision_rounding=self.currency_id.rounding,
            )
            >= 0
        )

    def _create_company_ehsan_donation_move(self):
        """Create company donation journal entry; does not change the customer invoice."""
        self.ensure_one()
        if not self._should_create_company_ehsan_donation():
            return self.env["account.move"]

        company = self.company_id
        if not (
            company.donation_debit_account_id
            and company.donation_credit_account_id
            and company.donation_journal_id
        ):
            _logger.warning(
                "Skip company Ehsan donation for invoice %s: donation accounts are not configured.",
                self.name,
            )
            return self.env["account.move"]

        amount = company.ehsan_company_donation_amount
        move = self.env["account.move"].sudo().create(
            {
                "move_type": "entry",
                "company_id": company.id,
                "journal_id": company.donation_journal_id.id,
                "date": fields.Date.context_today(self),
                "ref": _("Company Ehsan donation for %s") % self.name,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": _("Company Ehsan donation %s") % self.name,
                            "account_id": company.donation_debit_account_id.id,
                            "debit": amount,
                            "credit": 0.0,
                            "currency_id": self.currency_id.id,
                            "partner_id": self.partner_id.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": _("Company Ehsan donation %s") % self.name,
                            "account_id": company.donation_credit_account_id.id,
                            "debit": 0.0,
                            "credit": amount,
                            "currency_id": self.currency_id.id,
                            "partner_id": self.partner_id.id,
                        },
                    ),
                ],
            }
        )
        move.action_post()
        self.write(
            {
                "company_ehsan_donation_amount": amount,
                "company_ehsan_donation_move_id": move.id,
            }
        )
        return move


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    ehsan_donation_sale_order_id = fields.Many2one(
        "sale.order",
        string="Ehsan Donation Sales Order",
        copy=False,
        readonly=True,
        index=True,
        help="Technical link for an invoice-only Ehsan donation line.",
    )
