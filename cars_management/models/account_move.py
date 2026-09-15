# -*- coding: utf-8 -*-
import logging

from odoo import Command, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _needs_draft_invoice_accounting_sync(self):
        """True when draft invoice AMLs are incomplete vs invoice totals.

        Programmatic `_create_invoices()` can leave product balances filled
        (tax-excluded) while tax and receivable counterpart lines are missing.
        """
        self.ensure_one()
        product_lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type not in ("line_section", "line_note")
        )
        if not product_lines:
            return False
        currency = self.currency_id
        if any(currency.is_zero(abs(line.balance)) for line in product_lines):
            return True
        tax_amls = self.line_ids.filtered(
            lambda line: line.tax_line_id or line.display_type == "tax"
        )
        if any(line.tax_ids for line in product_lines) and not tax_amls:
            return True
        term_lines = self.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        )
        if self.amount_total:
            if not term_lines:
                return True
            counterpart = abs(sum(term_lines.mapped("amount_currency")))
            if currency.is_zero(counterpart):
                counterpart = abs(sum(term_lines.mapped("balance")))
            if not currency.is_zero(counterpart - self.amount_total):
                return True
        return False

    def _sync_draft_invoice_accounting(self):
        """Persist debit/credit and tax/receivable lines after programmatic create.

        Sale `_create_invoices()` can leave price_unit on invoice lines while
        stored balances stay 0, or extract included tax from revenue without
        creating the tax / receivable counterpart. Rewriting quantity follows
        the same path as saving the invoice form.
        """
        for invoice in self.filtered(
            lambda move: move.state == "draft" and move.is_invoice(include_receipts=True)
        ):
            if not invoice._needs_draft_invoice_accounting_sync():
                continue
            product_lines = invoice.invoice_line_ids.filtered(
                lambda line: line.display_type not in ("line_section", "line_note")
            )
            invoice.with_context(check_move_validity=False).write(
                {
                    "invoice_line_ids": [
                        Command.update(line.id, {"quantity": line.quantity})
                        for line in product_lines
                    ]
                }
            )

    def action_post(self):
        res = super().action_post()
        self._email_customer_invoices_after_post()
        return res

    def _email_customer_invoices_after_post(self):
        """Email customer invoices once the accountant posts them."""
        for move in self:
            if move.move_type != "out_invoice" or move.state != "posted":
                continue
            if move.is_move_sent:
                continue
            # Checkout / sale-origin invoices (and their upsell invoices)
            if not (move.invoice_line_ids.sale_line_ids or move.invoice_origin):
                continue
            move._send_customer_invoice_email()

    def _send_customer_invoice_email(self):
        """Send the standard invoice email; never block posting on mail errors."""
        self.ensure_one()
        if self.state != "posted":
            return
        if self.is_move_sent:
            return
        partner = self.partner_id
        if not (partner.email or "").strip():
            _logger.warning(
                "Skip invoice email for %s: partner %s has no email",
                self.name,
                partner.display_name,
            )
            return
        template = self.env.ref(
            "account.email_template_edi_invoice", raise_if_not_found=False
        )
        if not template:
            _logger.warning(
                "Invoice email template account.email_template_edi_invoice is missing"
            )
            return
        try:
            template.send_mail(self.id, force_send=True)
            self.is_move_sent = True
        except Exception:
            _logger.exception("Failed to email invoice %s", self.name)
