# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_loyalty_redeem_line = fields.Boolean(
        string="Loyalty Redeem Line",
        copy=False,
        default=False,
    )

    def unlink(self):
        if not self.env.context.get("loyalty_redeem_reversing"):
            for line in self.filtered("is_loyalty_redeem_line"):
                order = line.order_id
                points = order.loyalty_points_redeemed
                if points:
                    partner = order.partner_id.commercial_partner_id
                    card = partner._get_autochapeau_loyalty_card(create_if_missing=True)
                    if card:
                        card.points += points
                        if hasattr(partner, "_compute_loyalty"):
                            partner.invalidate_recordset(
                                [
                                    "loyalty_card_id",
                                    "loyalty_balance",
                                    "wallet_card_id",
                                    "wallet_balance",
                                ]
                            )
                    order.loyalty_points_redeemed = 0.0
                    order.loyalty_redeem_amount = 0.0
        return super().unlink()

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        if self.is_loyalty_redeem_line:
            # Keep discount untaxed on the invoice as well.
            res["tax_ids"] = [(5, 0, 0)]
        return res
