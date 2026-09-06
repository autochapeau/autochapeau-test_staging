# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


PAYMENT_BRANDS = [
    ("visa", "Visa"),
    ("mada", "Mada"),
    ("applepay", "Apple Pay"),
    ("googlepay", "Google Pay"),
    ("stc", "STC Pay"),
]

BRAND_TO_LOG_TYPE = {
    "visa": "wallet_topup_visa",
    "mada": "wallet_topup_mada",
    "applepay": "wallet_topup_applepay",
    "googlepay": "wallet_topup_googlepay",
    "stc": "wallet_topup_stc_web",
}


class WalletTopupRequest(models.Model):
    _name = "wallet.topup.request"
    _description = "Website Wallet Top-up Request"
    _order = "id desc"

    name = fields.Char(
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    amount = fields.Float(required=True)
    payment_brand = fields.Selection(
        selection=PAYMENT_BRANDS,
        required=True,
        string="Payment Brand",
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    transaction_id = fields.Char(
        string="Gateway Transaction ID",
        index=True,
        copy=False,
    )
    payment_id = fields.Many2one(
        "account.payment",
        string="Payment",
        readonly=True,
        copy=False,
    )
    wallet_card_id = fields.Many2one(
        "loyalty.card",
        string="Wallet Card",
        readonly=True,
        copy=False,
    )
    exchange_log_id = fields.Many2one(
        "loyalty.exchange.log",
        string="Exchange Log",
        readonly=True,
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("wallet.topup.request")
                    or _("New")
                )
        return super().create(vals_list)

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Top-up amount must be greater than zero."))

    def _get_or_create_wallet_card(self):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        card = partner.wallet_card_id
        if card:
            return card
        card = self.env["loyalty.card"].search(
            [
                ("partner_id", "=", partner.id),
                ("program_id.program_type", "=", "ewallet"),
                ("program_id.active", "=", True),
            ],
            limit=1,
        )
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

    def _get_bank_journal(self):
        self.ensure_one()
        journal = self.env["account.journal"].search(
            [
                ("type", "=", "bank"),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not journal:
            raise UserError(_("No bank journal found for company %s.") % self.company_id.display_name)
        return journal

    def action_confirm_website_payment(self, transaction_id):
        """Credit wallet after successful HyperPay / OPPWA payment."""
        self.ensure_one()
        if self.state == "done":
            return self
        if self.state != "pending":
            raise UserError(_("Only pending top-up requests can be confirmed."))
        if not transaction_id:
            raise UserError(_("transaction_id is required."))

        duplicate = self.sudo().search(
            [
                ("transaction_id", "=", transaction_id),
                ("state", "=", "done"),
                ("id", "!=", self.id),
            ],
            limit=1,
        )
        if duplicate:
            raise UserError(_("This transaction_id was already used for another top-up."))

        partner = self.partner_id.commercial_partner_id
        wallet_card = self._get_or_create_wallet_card()
        journal = self._get_bank_journal()
        brand_label = dict(PAYMENT_BRANDS).get(self.payment_brand, self.payment_brand)
        payment_ref = _("Website wallet top-up (%s) %s") % (brand_label, transaction_id)

        payment_vals = {
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner.id,
            "amount": self.amount,
            "date": fields.Date.context_today(self),
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "currency_id": self.company_id.currency_id.id,
            "ref": payment_ref,
        }
        method_line = journal.inbound_payment_method_line_ids[:1]
        if method_line:
            payment_vals["payment_method_line_id"] = method_line.id

        payment = self.env["account.payment"].sudo().create(payment_vals)
        payment.action_post()

        wallet_card.points += self.amount
        log_type = BRAND_TO_LOG_TYPE.get(self.payment_brand, "wallet_topup_card")
        log = self.env["loyalty.exchange.log"].sudo().create(
            {
                "partner_id": partner.id,
                "type": log_type,
                "points": self.amount,
                "amount": self.amount,
                "card_destination_id": wallet_card.id,
                "payment_id": payment.id,
            }
        )
        self.write(
            {
                "state": "done",
                "transaction_id": transaction_id,
                "payment_id": payment.id,
                "wallet_card_id": wallet_card.id,
                "exchange_log_id": log.id,
            }
        )
        return self
