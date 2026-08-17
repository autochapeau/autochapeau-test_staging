# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round

from .constants import LOYALTY_POINTS_PER_CURRENCY, LOYALTY_TYPE_SELECTION

# 10 loyalty points = 1 currency unit (SAR)
# LOYALTY_POINTS_PER_CURRENCY imported from constants


class SaleOrder(models.Model):
    _inherit = "sale.order"

    loyalty_type = fields.Selection(
        selection=LOYALTY_TYPE_SELECTION,
        string="Loyalty Points Destination",
        default="autochapeau",
        tracking=True,
        help="Where earned loyalty points should be credited when the invoice is paid.",
    )
    loyalty_balance = fields.Float(
        string="Loyalty Balance",
        compute="_compute_loyalty_redeem_info",
    )
    loyalty_points_redeemed = fields.Float(
        string="Loyalty Points Redeemed",
        copy=False,
        readonly=True,
    )
    loyalty_redeem_amount = fields.Monetary(
        string="Loyalty Redeem Amount",
        currency_field="currency_id",
        copy=False,
        readonly=True,
    )
    has_loyalty_redeem = fields.Boolean(
        compute="_compute_loyalty_redeem_info",
    )

    @api.onchange("partner_id")
    def _onchange_partner_id_loyalty_type(self):
        partner = self.partner_id.commercial_partner_id
        if partner and partner.preferred_loyalty_type:
            self.loyalty_type = partner.preferred_loyalty_type

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("loyalty_type") and vals.get("partner_id"):
                partner = self.env["res.partner"].browse(vals["partner_id"]).commercial_partner_id
                vals["loyalty_type"] = partner.preferred_loyalty_type or "autochapeau"
        return super().create(vals_list)

    @api.depends(
        "partner_id",
        "partner_id.loyalty_balance",
        "loyalty_points_redeemed",
        "order_line.is_loyalty_redeem_line",
    )
    def _compute_loyalty_redeem_info(self):
        for order in self:
            partner = order.partner_id.commercial_partner_id
            order.loyalty_balance = partner.loyalty_balance if partner else 0.0
            order.has_loyalty_redeem = bool(
                order.loyalty_points_redeemed
                or order.order_line.filtered("is_loyalty_redeem_line")
            )

    def _get_point_changes(self):
        """Do not credit loyalty-card points on SO confirm.

        Points are granted later when the customer invoice is fully paid.
        Reward consumption (negative changes) still applies on confirm.
        """
        changes = super()._get_point_changes()
        result = {}
        for coupon, change in changes.items():
            if (
                change > 0
                and coupon.program_id
                and coupon.program_id.program_type == "loyalty"
            ):
                continue
            result[coupon] = change
        return result

    def _program_check_compute_points(self, programs):
        """Grant loyalty points according to the customer's membership level.

        Also compute money-mode points on untaxed amount before discount
        instead of Odoo's default taxed total after discount.
        """
        result = super()._program_check_compute_points(programs)
        for program in programs:
            program_result = result.get(program)
            if not program_result or "points" not in program_result:
                continue
            if program.program_type != "loyalty":
                continue
            if len(program.rule_ids) != 1:
                continue
            rule = program.rule_ids
            if rule.reward_point_mode != "money" or not rule.reward_point_amount:
                continue
            base_amount = self._get_loyalty_amount_before_discount()
            points = float_round(
                rule.reward_point_amount * base_amount,
                precision_digits=2,
                rounding_method="DOWN",
            )
            program_result["points"] = [points]

        partner = self.partner_id
        if partner.is_company or not partner.membership_id:
            return result
        membership = partner.membership_id
        for program in programs:
            program_result = result.get(program)
            if not program_result or "points" not in program_result:
                continue
            if len(program.rule_ids) != 1:
                continue
            rule = program.rule_ids
            line = rule.membership_point_ids.filtered(
                lambda mp: mp.membership_id == membership
            )[:1]
            points = program_result.get("points")
            if not line or not rule.reward_point_amount:
                continue
            if line.reward_point_amount <= 0:
                continue
            factor = line.reward_point_amount / rule.reward_point_amount
            if isinstance(points, list):
                program_result["points"] = [p * factor for p in points]
            elif isinstance(points, (int, float)):
                program_result["points"] = points * factor
        return result

    def _get_loyalty_amount_before_discount(self):
        """Untaxed amount before line discounts (extracts price-included tax)."""
        self.ensure_one()
        amount = 0.0
        for line in self.order_line:
            if line.display_type or getattr(line, "is_reward_line", False):
                continue
            if line.is_loyalty_redeem_line:
                continue
            if not line.product_id:
                continue
            taxes = line.tax_id
            if taxes:
                res = taxes.compute_all(
                    line.price_unit,
                    currency=self.currency_id,
                    quantity=line.product_uom_qty,
                    product=line.product_id,
                    partner=self.partner_id,
                )
                amount += res.get("total_excluded", 0.0)
            else:
                amount += line.price_unit * line.product_uom_qty
        return amount

    def _get_loyalty_redeem_max_amount(self):
        """Max untaxed amount that can be covered by loyalty redemption."""
        self.ensure_one()
        return sum(
            line.price_subtotal
            for line in self.order_line
            if not line.display_type
            and not line.is_loyalty_redeem_line
            and not getattr(line, "is_reward_line", False)
        )

    def _get_loyalty_redeem_max_points(self):
        """Max points = min(card balance, points needed to cover untaxed amount)."""
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        card = partner._get_autochapeau_loyalty_card(create_if_missing=False)
        balance = card.points if card else 0.0
        # If replacing an existing redeem, balance already had those points deducted —
        # include them so the user can keep / re-allocate up to the same amount.
        available = balance + self.loyalty_points_redeemed
        max_by_amount = self._get_loyalty_redeem_max_amount() * LOYALTY_POINTS_PER_CURRENCY
        return max(min(available, max_by_amount), 0.0)

    def _get_loyalty_redeem_product(self):
        return self.env.ref(
            "autochapeau_loyalty.product_product_loyalty_redeem",
            raise_if_not_found=False,
        )

    def action_open_loyalty_redeem_wizard(self):
        self.ensure_one()
        if self.order_type == "contract":
            raise UserError(_("Loyalty redemption is not available on Contract sale orders."))
        if self.state not in ("draft", "sent"):
            raise UserError(_("Loyalty points can only be redeemed on quotations."))
        return {
            "name": _("Redeem Loyalty Points"),
            "type": "ir.actions.act_window",
            "res_model": "sale.loyalty.redeem.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_sale_order_id": self.id,
            },
        }

    def action_remove_loyalty_redeem(self):
        for order in self:
            if order.order_type == "contract":
                raise UserError(_("Loyalty redemption is not available on Contract sale orders."))
            order._reverse_loyalty_points_redeem()
        return True

    def _apply_loyalty_points_redeem(self, points):
        """Deduct points and add an untaxed discount line on the SO."""
        self.ensure_one()
        if self.order_type == "contract":
            raise UserError(_("Loyalty redemption is not available on Contract sale orders."))
        if self.state not in ("draft", "sent"):
            raise UserError(_("Loyalty points can only be redeemed on quotations."))
        points = float_round(points, precision_digits=2)
        if float_compare(points, 0.0, precision_digits=2) <= 0:
            raise UserError(_("Enter a positive number of points."))

        max_points = self._get_loyalty_redeem_max_points()
        if float_compare(points, max_points, precision_digits=2) > 0:
            raise UserError(
                _("You can redeem at most %(max).2f points on this order.")
                % {"max": max_points}
            )

        partner = self.partner_id.commercial_partner_id
        card = partner._get_autochapeau_loyalty_card(create_if_missing=False)
        if not card:
            raise UserError(_("No loyalty card found for this customer."))

        # Replace previous redemption if any.
        if self.loyalty_points_redeemed or self.order_line.filtered("is_loyalty_redeem_line"):
            self._reverse_loyalty_points_redeem()
            card.invalidate_recordset(["points"])
            card = partner._get_autochapeau_loyalty_card(create_if_missing=False)

        if float_compare(points, card.points, precision_digits=2) > 0:
            raise UserError(
                _("Customer only has %(bal).2f loyalty points.")
                % {"bal": card.points}
            )

        amount = float_round(
            points / LOYALTY_POINTS_PER_CURRENCY,
            precision_rounding=self.currency_id.rounding,
        )
        if float_compare(amount, 0.0, precision_rounding=self.currency_id.rounding) <= 0:
            raise UserError(_("Discount amount must be positive."))

        product = self._get_loyalty_redeem_product()
        if not product:
            raise UserError(
                _("Loyalty redeem product is missing. Please upgrade autochapeau_loyalty.")
            )

        card.points -= points
        if hasattr(partner, "_compute_loyalty"):
            partner.invalidate_recordset(
                ["loyalty_card_id", "loyalty_balance", "wallet_card_id", "wallet_balance"]
            )

        self.order_line = [
            (
                0,
                0,
                {
                    "product_id": product.id,
                    "name": _("Loyalty Points Discount (%s pts)") % points,
                    "product_uom_qty": 1.0,
                    "price_unit": -amount,
                    "discount": 0.0,
                    "tax_id": [(5, 0, 0)],
                    "is_loyalty_redeem_line": True,
                },
            )
        ]
        self.loyalty_points_redeemed = points
        self.loyalty_redeem_amount = amount

        partner.loyalty_exchange_log_ids = [
            (
                0,
                0,
                {
                    "type": "loyalty_so_redeem",
                    "points": points,
                    "amount": amount,
                    "card_source_id": card.id,
                    "order_id": self.id,
                },
            )
        ]
        return True

    def _reverse_loyalty_points_redeem(self):
        for order in self:
            points = order.loyalty_points_redeemed
            redeem_lines = order.order_line.filtered("is_loyalty_redeem_line")
            if not points and not redeem_lines:
                continue
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
            redeem_lines.with_context(loyalty_redeem_reversing=True).unlink()
            order.loyalty_points_redeemed = 0.0
            order.loyalty_redeem_amount = 0.0

    def action_cancel(self):
        self._reverse_loyalty_points_redeem()
        return super().action_cancel()

    def _get_autochapeau_loyalty_points_for_amount(self, base_amount):
        """Compatibility wrapper — calculation lives on res.partner."""
        self.ensure_one()
        return self.partner_id._get_autochapeau_loyalty_points_for_amount(base_amount)
