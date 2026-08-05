# -*- coding: utf-8 -*-
from odoo import fields, models


class LoyaltyExchangeLog(models.Model):
    _inherit = "loyalty.exchange.log"

    type = fields.Selection(
        selection_add=[
            ("loyalty_so_redeem", "Loyalty points redeemed on Sale Order"),
            ("loyalty_alrajhi_earn", "Loyalty points earned on Alrajhi"),
            ("loyalty_qitaf_earn", "Loyalty points earned on Qitaf"),
        ],
        ondelete={
            "loyalty_so_redeem": "cascade",
            "loyalty_alrajhi_earn": "cascade",
            "loyalty_qitaf_earn": "cascade",
        },
    )
