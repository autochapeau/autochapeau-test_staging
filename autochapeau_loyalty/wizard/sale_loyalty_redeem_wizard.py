# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

from odoo.addons.autochapeau_loyalty.models.constants import LOYALTY_POINTS_PER_CURRENCY


class SaleLoyaltyRedeemWizard(models.TransientModel):
    _name = "sale.loyalty.redeem.wizard"
    _description = "Redeem Loyalty Points on Sale Order"

    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        readonly=True,
    )
    loyalty_balance = fields.Float(
        string="Available Points",
        readonly=True,
    )
    max_points = fields.Float(
        string="Max Redeemable Points",
        readonly=True,
    )
    redeem_all = fields.Boolean(
        string="Use All Available Points",
        default=False,
    )
    points = fields.Float(
        string="Points to Redeem",
        required=True,
    )
    discount_amount = fields.Monetary(
        string="Discount Amount (Untaxed)",
        currency_field="currency_id",
        compute="_compute_discount_amount",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env["sale.order"].browse(
            values.get("sale_order_id")
            or self.env.context.get("default_sale_order_id")
        )
        if order:
            # Balance shown includes points already reserved on this SO (if any).
            max_points = order._get_loyalty_redeem_max_points()
            partner = order.partner_id.commercial_partner_id
            card = partner._get_autochapeau_loyalty_card(create_if_missing=False)
            balance = (card.points if card else 0.0) + order.loyalty_points_redeemed
            values.setdefault("loyalty_balance", balance)
            values.setdefault("max_points", max_points)
            if "points" in fields_list and not values.get("points"):
                values["points"] = max_points
        return values

    @api.depends("points")
    def _compute_discount_amount(self):
        for wizard in self:
            wizard.discount_amount = (wizard.points or 0.0) / LOYALTY_POINTS_PER_CURRENCY

    @api.onchange("redeem_all")
    def _onchange_redeem_all(self):
        if self.redeem_all:
            self.points = self.max_points

    @api.onchange("points")
    def _onchange_points(self):
        if self.points and self.max_points and self.points > self.max_points:
            return {
                "warning": {
                    "title": _("Too many points"),
                    "message": _(
                        "Maximum redeemable points on this order: %(max).2f"
                    )
                    % {"max": self.max_points},
                }
            }

    def action_apply(self):
        self.ensure_one()
        order = self.sale_order_id
        points = self.max_points if self.redeem_all else self.points
        if float_compare(points, 0.0, precision_digits=2) <= 0:
            raise UserError(_("Enter a positive number of points."))
        if float_compare(points, self.max_points, precision_digits=2) > 0:
            raise UserError(
                _("You can redeem at most %(max).2f points.")
                % {"max": self.max_points}
            )
        order._apply_loyalty_points_redeem(points)
        return {"type": "ir.actions.act_window_close"}
