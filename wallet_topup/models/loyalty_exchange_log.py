# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LoyaltyExchangeLog(models.Model):
    _inherit = "loyalty.exchange.log"

    type = fields.Selection(
        selection_add=[
            ("wallet_topup_cash", "Wallet top-up (Cash)"),
            ("wallet_topup_card", "Wallet top-up (Card)"),
            ("wallet_topup_terminal", "Wallet top-up (Card Terminal)"),
            ("wallet_topup_stc", "Wallet top-up (STC Pay)"),
            ("wallet_topup_visa", "Wallet top-up (Visa)"),
            ("wallet_topup_mada", "Wallet top-up (Mada)"),
            ("wallet_topup_applepay", "Wallet top-up (Apple Pay)"),
            ("wallet_topup_googlepay", "Wallet top-up (Google Pay)"),
            ("wallet_topup_stc_web", "Wallet top-up (STC Pay - Website)"),
        ],
        ondelete={
            "wallet_topup_cash": "cascade",
            "wallet_topup_card": "cascade",
            "wallet_topup_terminal": "cascade",
            "wallet_topup_stc": "cascade",
            "wallet_topup_visa": "cascade",
            "wallet_topup_mada": "cascade",
            "wallet_topup_applepay": "cascade",
            "wallet_topup_googlepay": "cascade",
            "wallet_topup_stc_web": "cascade",
        },
    )
    direction = fields.Selection(
        selection=[
            ("in", "In"),
            ("out", "Out"),
        ],
        compute="_compute_direction",
        store=True,
    )
    payment_id = fields.Many2one(
        "account.payment",
        string="Payment",
        ondelete="set null",
        readonly=True,
    )

    @api.depends("type")
    def _compute_direction(self):
        out_types = {
            "payment_by_wallet",
            "loyalty_so_redeem",
        }
        in_types = {
            "loyalty_exchange",
            "alrajhi_loyalty_exchange",
            "qitaf_loyalty_exchange",
            "yougotagift_loyalty_exchange",
            "mylist_loyalty_exchange",
            "loyalty_invoice_earn",
            "loyalty_alrajhi_earn",
            "loyalty_qitaf_earn",
            "wallet_topup_cash",
            "wallet_topup_card",
            "wallet_topup_terminal",
            "wallet_topup_stc",
            "wallet_topup_visa",
            "wallet_topup_mada",
            "wallet_topup_applepay",
            "wallet_topup_googlepay",
            "wallet_topup_stc_web",
        }
        for log in self:
            if log.type in out_types:
                log.direction = "out"
            elif log.type in in_types:
                log.direction = "in"
            elif not log.direction:
                log.direction = False
