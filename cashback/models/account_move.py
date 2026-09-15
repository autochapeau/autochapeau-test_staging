# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    cashback_program_id = fields.Many2one(
        "cashback.program",
        string="Cashback Program",
        copy=False,
        readonly=True,
    )
    cashback_amount_granted = fields.Monetary(
        string="Cashback Granted",
        currency_field="currency_id",
        copy=False,
        readonly=True,
        help="Wallet cashback credited when this invoice was posted.",
    )
    cashback_done = fields.Boolean(
        string="Cashback Done",
        copy=False,
        readonly=True,
        help="Cashback was already granted for this invoice.",
    )

    def action_post(self):
        res = super().action_post()
        self._grant_cashback_to_wallet(source="action_post")
        return res

    def button_draft(self):
        self._reverse_cashback_from_wallet()
        return super().button_draft()

    def button_cancel(self):
        self._reverse_cashback_from_wallet()
        return super().button_cancel()

    def _get_cashback_sale_orders(self):
        self.ensure_one()
        return self.invoice_line_ids.sale_line_ids.order_id

    def _is_cashback_eligible_order(self, order):
        """Intern/extern orders are eligible; contract parents are not.

        Contract sub/extra orders keep order_type intern/extern and are eligible.
        """
        return order.order_type in ("intern", "extern")

    def _get_cashback_base_amount(self, program):
        self.ensure_one()
        if program.amount_basis == "total":
            return self.amount_total
        return self.amount_untaxed

    def _get_or_create_wallet_card(self, partner):
        """Return partner eWallet card, creating it from company program if needed."""
        self.ensure_one()
        partner = partner.commercial_partner_id
        if partner.wallet_card_id:
            return partner.wallet_card_id

        program = (
            self.company_id.wallet_program_id
            or partner.company_id.wallet_program_id
            or self.env.company.wallet_program_id
        )
        if not program:
            _logger.warning(
                "[cashback] No wallet program configured; cannot credit partner %s",
                partner.display_name,
            )
            return self.env["loyalty.card"]

        card = self.env["loyalty.card"].sudo().with_context(
            loyalty_no_mail=True,
            tracking_disable=True,
        ).create(
            {
                "program_id": program.id,
                "partner_id": partner.id,
                "points": 0,
            }
        )
        partner.invalidate_recordset(
            ["wallet_card_id", "wallet_balance", "loyalty_card_ids"]
        )
        return card

    def _compute_cashback_amount(self, program):
        self.ensure_one()
        base = self._get_cashback_base_amount(program)
        if base <= 0:
            return 0.0
        amount = base * (program.percentage / 100.0)
        return self.currency_id.round(amount)

    def _grant_cashback_to_wallet(self, source="unknown"):
        Program = self.env["cashback.program"]
        for move in self:
            prefix = "[cashback] move=%s(%s)" % (move.id, move.name or "draft")
            if move.move_type != "out_invoice" or move.state != "posted":
                continue
            if move.cashback_done or move.cashback_amount_granted:
                _logger.info("%s skip: already granted", prefix)
                continue

            sale_orders = move._get_cashback_sale_orders()
            if not sale_orders:
                _logger.info("%s skip: no linked sale orders", prefix)
                continue
            if sale_orders.filtered(lambda order: order.order_type == "contract"):
                _logger.info("%s skip: contract parent order", prefix)
                continue
            if not sale_orders.filtered(move._is_cashback_eligible_order):
                _logger.info("%s skip: no intern/extern sale orders", prefix)
                continue

            invoice_date = move.invoice_date or fields.Date.context_today(move)
            program = Program._get_active_program(move.company_id, on_date=invoice_date)
            if not program:
                _logger.info("%s skip: no active cashback program on %s", prefix, invoice_date)
                continue

            cashback_amount = move._compute_cashback_amount(program)
            if cashback_amount <= 0:
                _logger.info("%s skip: cashback_amount <= 0", prefix)
                continue

            partner = move.partner_id.commercial_partner_id
            wallet_card = move._get_or_create_wallet_card(partner)
            if not wallet_card:
                continue

            wallet_card.points += cashback_amount
            partner.invalidate_recordset(["wallet_card_id", "wallet_balance"])

            order = sale_orders.filtered(move._is_cashback_eligible_order)[:1]
            self.env["loyalty.exchange.log"].sudo().create(
                {
                    "partner_id": partner.id,
                    "type": "cashback_invoice_earn",
                    "points": cashback_amount,
                    "amount": cashback_amount,
                    "card_destination_id": wallet_card.id,
                    "order_id": order.id if order else False,
                    "invoice_id": move.id,
                }
            )

            move.write(
                {
                    "cashback_program_id": program.id,
                    "cashback_amount_granted": cashback_amount,
                    "cashback_done": True,
                }
            )
            _logger.info(
                "%s granted=%s program=%s source=%s",
                prefix,
                cashback_amount,
                program.display_name,
                source,
            )

            try:
                move._notify_cashback(partner, program, cashback_amount, wallet_card.points)
            except Exception:
                _logger.exception(
                    "%s notification failed after wallet credit",
                    prefix,
                )

    def _reverse_cashback_from_wallet(self):
        for move in self:
            if not move.cashback_done or not move.cashback_amount_granted:
                continue
            partner = move.partner_id.commercial_partner_id
            wallet_card = partner.wallet_card_id
            amount = move.cashback_amount_granted
            if wallet_card and amount:
                wallet_card.points = max(wallet_card.points - amount, 0.0)
                partner.invalidate_recordset(["wallet_card_id", "wallet_balance"])
                self.env["loyalty.exchange.log"].sudo().create(
                    {
                        "partner_id": partner.id,
                        "type": "cashback_invoice_reverse",
                        "points": amount,
                        "amount": amount,
                        "card_source_id": wallet_card.id,
                        "order_id": move._get_cashback_sale_orders()[:1].id,
                        "invoice_id": move.id,
                    }
                )
            move.write(
                {
                    "cashback_amount_granted": 0.0,
                    "cashback_done": False,
                    "cashback_program_id": False,
                }
            )

    def _notify_cashback(self, partner, program, cashback_amount, wallet_balance):
        self.ensure_one()
        if not program.notify_sms and not program.notify_whatsapp:
            return
        message = program._format_notification_message(
            partner, self, cashback_amount, wallet_balance
        )
        if program.notify_sms:
            self._send_cashback_sms(partner, message)
        if program.notify_whatsapp:
            self._send_cashback_whatsapp(partner, message)

    def _send_cashback_sms(self, partner, message):
        """Send cashback SMS via Infinito helper on res.partner."""
        partner = partner.commercial_partner_id
        mobile = partner.mobile or partner.phone
        if not mobile:
            _logger.info(
                "[cashback] no mobile on partner %s; skip SMS",
                partner.display_name,
            )
            return False
        if not hasattr(partner, "_send_otp_sms_message"):
            _logger.warning("[cashback] SMS helper missing on res.partner")
            return False
        phone = partner._format_phone_for_sms(mobile, partner.country_id)
        if not phone:
            return False
        try:
            return partner._send_otp_sms_message(phone, message, partner=partner)
        except Exception:
            _logger.exception(
                "[cashback] SMS failed for partner %s",
                partner.display_name,
            )
            return False

    def _send_cashback_whatsapp(self, partner, message):
        """WhatsApp hook.

        No WhatsApp provider exists in this codebase yet. Post on the partner
        chatter so the attempt is auditable; override this method when a
        WhatsApp gateway is available.
        """
        partner = partner.commercial_partner_id
        partner.message_post(
            body=_("WhatsApp cashback notification (pending provider): %s") % message,
            subject=_("Cashback WhatsApp"),
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
        _logger.info(
            "[cashback] WhatsApp provider not configured; chatter note for partner %s",
            partner.display_name,
        )
        return False

    def action_grant_cashback(self):
        """Manual button for posted invoices that missed automatic cashback."""
        for move in self:
            if move.move_type != "out_invoice":
                raise UserError(_("Cashback can only be granted on customer invoices."))
            if move.state != "posted":
                raise UserError(_("The invoice must be posted."))
            if move.cashback_done or move.cashback_amount_granted:
                raise UserError(_("Cashback was already granted on this invoice."))
            sale_orders = move._get_cashback_sale_orders()
            if sale_orders.filtered(lambda order: order.order_type == "contract"):
                raise UserError(_("Cashback is not granted for Contract sale orders."))
        self._grant_cashback_to_wallet(source="manual_button")
        missing = self.filtered(lambda move: not move.cashback_done)
        if missing:
            raise UserError(
                _(
                    "Could not grant cashback. Check that an active cashback program "
                    "covers the invoice date and that the sale order is Intern/Extern."
                )
            )
        return True
