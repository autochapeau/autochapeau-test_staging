# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.tools import format_amount


class LoyaltyCard(models.Model):
    _inherit = "loyalty.card"

    exchange_log_count = fields.Integer(
        string="Wallet History",
        compute="_compute_exchange_log_count",
    )

    def _compute_exchange_log_count(self):
        Log = self.env["loyalty.exchange.log"].sudo()
        for card in self:
            card.exchange_log_count = Log.search_count(
                [
                    "|",
                    ("card_source_id", "=", card.id),
                    ("card_destination_id", "=", card.id),
                ]
            )

    def action_view_wallet_log(self):
        """Open exchange history linked to this card (wallet or loyalty)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Wallet History"),
            "res_model": "loyalty.exchange.log",
            "view_mode": "tree,form",
            "domain": [
                "|",
                ("card_source_id", "=", self.id),
                ("card_destination_id", "=", self.id),
            ],
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_card_source_id": self.id,
            },
        }

    def _format_points(self, points):
        """Avoid crash when program has no currency (e.g. archived cards)."""
        self.ensure_one()
        currency = self.program_id.currency_id
        if currency and self.point_name == currency.symbol:
            return format_amount(self.env, points, currency)
        if points == int(points):
            return f"{int(points)} {self.point_name or ''}"
        return f"{points:.2f} {self.point_name or ''}"
