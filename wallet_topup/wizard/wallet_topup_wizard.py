# -*- coding: utf-8 -*-
import logging
import uuid
import warnings

import requests
import urllib3

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")


class WalletTopupWizard(models.TransientModel):
    _name = "wallet.topup.wizard"
    _description = "Wallet Top-up Wizard"

    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
    )
    wallet_card_id = fields.Many2one(
        "loyalty.card",
        string="Wallet Card",
        domain="[('partner_id', '=', partner_id), ('program_id.program_type', '=', 'ewallet')]",
    )
    wallet_balance = fields.Float(
        string="Current Balance",
        related="wallet_card_id.points",
        readonly=True,
    )
    amount = fields.Float(
        string="Top-up Amount",
        required=True,
    )
    payment_method = fields.Selection(
        selection=[
            ("cash", "Cash"),
            ("card", "Card (manual)"),
            ("card_terminal", "Card Terminal"),
            ("stc", "STC Pay"),
        ],
        string="Payment Method",
        required=True,
        default="cash",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        required=True,
        check_company=True,
        domain="[('type', 'in', ('cash', 'bank'))]",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    note = fields.Char(string="Reference / Note")
    terminal_reference = fields.Char(readonly=True)

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if not self.partner_id:
            self.wallet_card_id = False
            return
        partner = self.partner_id.commercial_partner_id
        card = partner.wallet_card_id
        if not card:
            card = self.env["loyalty.card"].search(
                [
                    ("partner_id", "=", partner.id),
                    ("program_id.program_type", "=", "ewallet"),
                    ("program_id.active", "=", True),
                ],
                limit=1,
            )
        self.wallet_card_id = card

    @api.onchange("payment_method", "company_id")
    def _onchange_payment_method(self):
        journal_type = "cash" if self.payment_method == "cash" else "bank"
        journal = self.env["account.journal"].search(
            [
                ("type", "=", journal_type),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        # Prefer Card Terminal collection method journal when available.
        if self.payment_method == "card_terminal":
            method = self.env["sale.collection.method"].search(
                [
                    ("code", "=", "card_terminal"),
                    ("company_id", "=", self.company_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if method and method.journal_id:
                journal = method.journal_id
        self.journal_id = journal

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        res.setdefault("company_id", company.id)
        payment_method = res.get("payment_method") or "cash"
        journal_type = "cash" if payment_method == "cash" else "bank"
        journal = self.env["account.journal"].search(
            [
                ("type", "=", journal_type),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        if journal and "journal_id" in fields_list:
            res["journal_id"] = journal.id
        partner_id = res.get("partner_id") or self.env.context.get("default_partner_id")
        if partner_id:
            partner = self.env["res.partner"].browse(partner_id).commercial_partner_id
            res["partner_id"] = partner.id
            wallet_card = res.get("wallet_card_id") or self.env.context.get(
                "default_wallet_card_id"
            )
            if not wallet_card:
                wallet_card = partner.wallet_card_id.id
            if wallet_card:
                res["wallet_card_id"] = wallet_card
        return res

    def _get_or_create_wallet_card(self):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        card = self.wallet_card_id
        if card and card.partner_id == partner and card.program_type == "ewallet":
            return card
        card = partner.wallet_card_id
        if card:
            return card
        program = self.company_id.wallet_program_id
        if not program:
            program = self.env["loyalty.program"].search(
                [
                    ("program_type", "=", "ewallet"),
                    ("active", "=", True),
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
        if not program:
            raise UserError(
                _("No eWallet program configured. Set Default Wallet Program on the company.")
            )
        return (
            self.env["loyalty.card"]
            .sudo()
            .with_context(loyalty_no_mail=True, tracking_disable=True)
            .create(
                {
                    "program_id": program.id,
                    "partner_id": partner.id,
                    "points": 0,
                }
            )
        )

    def _log_type_for_method(self):
        return {
            "cash": "wallet_topup_cash",
            "card": "wallet_topup_card",
            "card_terminal": "wallet_topup_terminal",
            "stc": "wallet_topup_stc",
        }[self.payment_method]

    def _get_config(self, key, default=False):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    def _terminal_headers(self):
        token = self._get_config("sale_split_payment.card_terminal_token")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        return headers

    def _terminal_timeout(self):
        try:
            return max(
                int(self._get_config("sale_split_payment.card_terminal_timeout", 60)),
                1,
            )
        except (TypeError, ValueError):
            return 60

    def _new_terminal_reference(self):
        return "WT/%s" % uuid.uuid4().hex[:10].upper()

    def _send_card_terminal_charge(self, reference):
        """Charge SoftPOS using the same connector as Collect Payment."""
        self.ensure_one()
        terminal_url = self._get_config("sale_split_payment.card_terminal_url")
        if not terminal_url:
            raise UserError(_("Card terminal API URL is not configured."))

        partner = self.partner_id.commercial_partner_id
        payload = {
            "amount": "%.2f" % float(self.amount),
            "transaction_type": "Sale",
            "paymentApp": "softpos",
            "reference": reference,
            "transactionRefNo": reference,
            "currency": self.currency_id.name,
            "sale_order": reference,
            "partner": partner.name,
        }
        try:
            response = requests.post(
                terminal_url,
                json=payload,
                headers=self._terminal_headers(),
                timeout=self._terminal_timeout(),
                verify=False,
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            _logger.exception("Wallet top-up card terminal request failed")
            raise UserError(_("Card terminal error: %s") % error) from error

        status = str(result.get("status", "")).lower()
        response_code = str(result.get("responseCode") or "").strip()
        is_failed = result.get("isFailed")
        if isinstance(is_failed, str):
            is_failed = is_failed.strip().lower() in ("1", "true", "yes")

        softpos_approved = (
            not is_failed
            and response_code == "000"
            and bool(result.get("approvalCode"))
        )
        if softpos_approved or status in ("approved", "success", "paid", "completed"):
            txn_ref = (
                result.get("transaction_id")
                or result.get("txnId")
                or result.get("rrNumber")
                or result.get("reference")
                or result.get("approvalCode")
                or reference
            )
            return {
                "ok": True,
                "reference": txn_ref,
                "approval_code": result.get("approvalCode") or False,
                "raw": result,
            }

        message = (
            result.get("message")
            or result.get("errorMessage")
            or _("Card terminal declined or failed the payment.")
        )
        raise UserError(message)

    def _create_payment_and_credit_wallet(self, wallet_card, payment_ref):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        amount = self.amount
        payment_vals = {
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner.id,
            "amount": amount,
            "date": fields.Date.context_today(self),
            "journal_id": self.journal_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "ref": payment_ref,
        }
        method_line = self.journal_id.inbound_payment_method_line_ids[:1]
        if method_line:
            payment_vals["payment_method_line_id"] = method_line.id

        payment = self.env["account.payment"].sudo().create(payment_vals)
        payment.action_post()

        wallet_card.points += amount
        self.env["loyalty.exchange.log"].sudo().create(
            {
                "partner_id": partner.id,
                "type": self._log_type_for_method(),
                "points": amount,
                "amount": amount,
                "card_destination_id": wallet_card.id,
                "payment_id": payment.id,
            }
        )
        return payment

    def action_confirm(self):
        self.ensure_one()
        if self.amount <= 0:
            raise UserError(_("Top-up amount must be greater than zero."))
        if not self.journal_id:
            raise UserError(_("Please select a payment journal."))

        partner = self.partner_id.commercial_partner_id
        wallet_card = self._get_or_create_wallet_card()
        method_label = dict(self._fields["payment_method"].selection).get(
            self.payment_method
        )
        ref = self.note or _("Wallet top-up (%s)") % method_label

        if self.payment_method == "card_terminal":
            terminal_ref = self._new_terminal_reference()
            self.terminal_reference = terminal_ref
            terminal_result = self._send_card_terminal_charge(terminal_ref)
            ref = _(
                "Wallet top-up (Card Terminal) %(ref)s / approval %(approval)s"
            ) % {
                "ref": terminal_result["reference"],
                "approval": terminal_result.get("approval_code") or "-",
            }

        self._create_payment_and_credit_wallet(wallet_card, ref)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Wallet topped up"),
                "message": _(
                    "Added %(amount)s to %(partner)s wallet. New balance: %(balance)s"
                )
                % {
                    "amount": self.amount,
                    "partner": partner.display_name,
                    "balance": wallet_card.points,
                },
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
