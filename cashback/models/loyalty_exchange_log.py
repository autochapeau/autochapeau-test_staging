# -*- coding: utf-8 -*-
from odoo import fields, models


class LoyaltyExchangeLog(models.Model):
    _inherit = "loyalty.exchange.log"

    type = fields.Selection(
        selection_add=[
            ("cashback_invoice_earn", "Cashback from invoice"),
            ("cashback_invoice_reverse", "Cashback reverse"),
        ],
        ondelete={
            "cashback_invoice_earn": "cascade",
            "cashback_invoice_reverse": "cascade",
        },
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Invoice",
        ondelete="set null",
        index=True,
    )
