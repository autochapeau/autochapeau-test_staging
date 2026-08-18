import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ehsan_donation_amount = fields.Monetary(
        string="Ehsan Donation Amount",
        currency_field="currency_id",
        copy=False,
        help="Donation amount set from the ERP Ehsan donation wizard.",
    )
    ehsan_donation_move_id = fields.Many2one(
        "account.move",
        string="Ehsan Donation Journal Entry",
        copy=False,
        readonly=True,
        check_company=True,
    )
    ehsan_donation_invoice_id = fields.Many2one(
        "account.move",
        string="Ehsan Donation Invoice",
        copy=False,
        readonly=True,
        check_company=True,
        help="Customer invoice containing the Ehsan donation line.",
    )
    ehsan_donation_state = fields.Selection(
        selection=[
            ("pending", "Pending Journal"),
            ("posted", "Posted"),
        ],
        string="Ehsan Donation Status",
        compute="_compute_ehsan_donation_state",
        store=True,
        copy=False,
    )
    company_ehsan_donation_amount = fields.Monetary(
        string="Company Ehsan Donation",
        currency_field="currency_id",
        copy=False,
        readonly=True,
        help="Company donation generated once when paid invoices of this order reach the threshold.",
    )
    company_ehsan_donation_move_id = fields.Many2one(
        "account.move",
        string="Company Ehsan Donation Journal Entry",
        copy=False,
        readonly=True,
        check_company=True,
    )
    ehsan_donation_declined = fields.Boolean(
        string="Customer Declined Ehsan Donation",
        copy=False,
        help="Customer does not want to donate. Hides the Ehsan Donation button.",
    )

    @api.depends(
        "transaction_ids",
        "transaction_ids.donation_amount",
        "ehsan_donation_amount",
    )
    def _compute_donation_amount(self):
        """Total donation = web payment donations + ERP wizard donation."""
        for order in self:
            tx_total = sum(order.transaction_ids.mapped("donation_amount"))
            order.donation_amount = tx_total + (order.ehsan_donation_amount or 0.0)

    @api.depends(
        "ehsan_donation_amount",
        "ehsan_donation_move_id",
        "ehsan_donation_invoice_id.payment_state",
    )
    def _compute_ehsan_donation_state(self):
        for order in self:
            if (
                order.ehsan_donation_move_id
                or (
                    order.ehsan_donation_invoice_id
                    and order.ehsan_donation_invoice_id.payment_state
                    in ("paid", "in_payment")
                )
            ):
                order.ehsan_donation_state = "posted"
            elif order.ehsan_donation_amount:
                order.ehsan_donation_state = "pending"
            else:
                order.ehsan_donation_state = False

    @api.depends(
        "amount_total",
        "ehsan_donation_amount",
        "split_payment_ids.amount",
        "split_payment_ids.state",
    )
    def _compute_split_payment_totals(self):
        super()._compute_split_payment_totals()
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
                    lambda payment: payment.state
                    in ("processing", "pending", "needs_review")
                ).mapped("amount")
            )
            amount_to_collect = (
                order.amount_total + (order.ehsan_donation_amount or 0.0)
            )
            order.split_amount_remaining = max(
                amount_to_collect - paid - pending,
                0.0,
            )

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super()._create_invoices(
            grouped=grouped,
            final=final,
            date=date,
        )
        self._add_ehsan_donation_to_invoices(invoices)
        return invoices

    def _add_ehsan_donation_to_invoices(self, invoices):
        """Add the customer donation to one invoice, never to sale order lines."""
        for order in self.filtered(
            lambda sale: sale.order_type != "contract"
            and sale.ehsan_donation_amount > 0
        ):
            existing_line = order.invoice_ids.invoice_line_ids.filtered(
                lambda line: line.ehsan_donation_sale_order_id == order
            )
            if existing_line:
                order.ehsan_donation_invoice_id = existing_line[:1].move_id.id
                continue

            order_invoices = invoices.filtered(
                lambda invoice: order
                in invoice.invoice_line_ids.sale_line_ids.order_id
                and invoice.move_type == "out_invoice"
            )
            invoice = order_invoices[:1]
            if not invoice:
                continue

            account = order.company_id.donation_credit_account_id
            if not account:
                raise UserError(
                    _(
                        "Please configure the Donation Credit Account before "
                        "creating an invoice with an Ehsan donation."
                    )
                )
            invoice.write(
                {
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": _("تبرع لإحسان"),
                                "quantity": 1.0,
                                "price_unit": order.ehsan_donation_amount,
                                "product_id": False,
                                "product_uom_id": False,
                                "account_id": account.id,
                                "tax_ids": [(5, 0, 0)],
                                "ehsan_donation_sale_order_id": order.id,
                            },
                        )
                    ]
                }
            )
            order.ehsan_donation_invoice_id = invoice.id

    def action_open_ehsan_donation_wizard(self):
        self.ensure_one()
        if self.order_type == "contract":
            raise UserError(_(
                "Ehsan donations are not available on Contract sale orders."
            ))
        if self.ehsan_donation_move_id:
            raise UserError(
                _(
                    "An Ehsan donation journal entry already exists for this order. "
                    "You cannot change the donation amount anymore."
                )
            )
        return {
            "name": _("Ehsan Donation"),
            "type": "ir.actions.act_window",
            "res_model": "ehsan.donation.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_sale_order_id": self.id,
                "default_donation_amount": self.ehsan_donation_amount or 10.0,
            },
        }

    def _create_ehsan_donation_move(self):
        """Create and post donation journal entry using company donation accounts."""
        self.ensure_one()
        if self.order_type == "contract":
            return self.env["account.move"]
        amount = self.ehsan_donation_amount or 0.0
        if amount <= 0:
            return self.env["account.move"]
        if self.ehsan_donation_move_id:
            return self.ehsan_donation_move_id

        company = self.company_id
        if not (
            company.donation_debit_account_id
            and company.donation_credit_account_id
            and company.donation_journal_id
        ):
            raise UserError(
                _(
                    "Please configure Donation Debit Account, Donation Credit Account "
                    "and Donation Journal in Accounting settings before posting "
                    "Ehsan donations."
                )
            )

        move = self.env["account.move"].sudo().create(
            {
                "move_type": "entry",
                "company_id": company.id,
                "journal_id": company.donation_journal_id.id,
                "date": fields.Date.context_today(self),
                "ref": _("Ehsan donation for %s") % self.name,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": _("Ehsan donation %s") % self.name,
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
                            "name": _("Ehsan donation %s") % self.name,
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
        self.ehsan_donation_move_id = move.id
        return move

    def _get_paid_customer_invoice_total(self):
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda move: move.move_type == "out_invoice"
            and move.state == "posted"
            and move.payment_state in ("paid", "in_payment")
        )
        return sum(invoices.mapped("amount_untaxed"))

    def _create_company_ehsan_donation_move(self, trigger_invoice=None):
        """Donate once per sales order when paid invoices reach the threshold."""
        self.ensure_one()
        if self.order_type == "contract":
            return self.env["account.move"]
        if self.company_ehsan_donation_move_id:
            return self.company_ehsan_donation_move_id

        company = self.company_id
        if not company.ehsan_company_donation_enabled:
            return self.env["account.move"]
        amount = company.ehsan_company_donation_amount or 0.0
        threshold = company.ehsan_company_donation_threshold or 0.0
        rounding = self.currency_id.rounding
        if float_compare(amount, 0.0, precision_rounding=rounding) <= 0:
            return self.env["account.move"]
        paid_total = self._get_paid_customer_invoice_total()
        if float_compare(paid_total, threshold, precision_rounding=rounding) < 0:
            return self.env["account.move"]
        if not (
            company.donation_debit_account_id
            and company.donation_credit_account_id
            and company.donation_journal_id
        ):
            _logger.warning(
                "Skip company Ehsan donation for order %s: donation accounts are not configured.",
                self.name,
            )
            return self.env["account.move"]

        origin = trigger_invoice.name if trigger_invoice else self.name
        move = self.env["account.move"].sudo().create(
            {
                "move_type": "entry",
                "company_id": company.id,
                "journal_id": company.donation_journal_id.id,
                "date": fields.Date.context_today(self),
                "ref": _("Company Ehsan donation for %s") % origin,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": _("Company Ehsan donation %s") % origin,
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
                            "name": _("Company Ehsan donation %s") % origin,
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
        self.company_ehsan_donation_amount = amount
        self.company_ehsan_donation_move_id = move.id
        if trigger_invoice and not trigger_invoice.company_ehsan_donation_move_id:
            trigger_invoice.write(
                {
                    "company_ehsan_donation_amount": amount,
                    "company_ehsan_donation_move_id": move.id,
                }
            )
        return move
