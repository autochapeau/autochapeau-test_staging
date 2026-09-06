# -*- coding: utf-8 -*-
from odoo import _, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_open_wallet_topup(self):
        self.ensure_one()
        partner = self.commercial_partner_id
        return {
            "type": "ir.actions.act_window",
            "name": _("Wallet Top-up"),
            "res_model": "wallet.topup.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": partner.id,
            },
        }
