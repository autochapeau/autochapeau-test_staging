# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class LoyaltyCard(models.Model):
    _inherit = "loyalty.card"

    def action_open_wallet_topup(self):
        self.ensure_one()
        if self.program_type != "ewallet":
            raise UserError(_("Top-up is only available on eWallet cards."))
        if not self.partner_id:
            raise UserError(_("This wallet card has no partner."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Wallet Top-up"),
            "res_model": "wallet.topup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_wallet_card_id": self.id,
            },
        }
