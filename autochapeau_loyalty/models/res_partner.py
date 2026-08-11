# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_round

from .constants import LOYALTY_TYPE_SELECTION

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    preferred_loyalty_type = fields.Selection(
        selection=LOYALTY_TYPE_SELECTION,
        string="Preferred Loyalty Program",
        default="autochapeau",
        help="Default destination for loyalty points earned on paid invoices. "
        "Can be overridden per Sale Order.",
    )
    loyalty_card_count = fields.Integer(
        string="Loyalty Cards",
        compute="_compute_loyalty_card_count",
    )

    def _compute_loyalty_card_count(self):
        Card = self.env["loyalty.card"].sudo()
        for partner in self:
            partner.loyalty_card_count = Card.search_count(
                [
                    ("partner_id", "=", partner.commercial_partner_id.id),
                    ("program_id.program_type", "=", "loyalty"),
                ]
            )

    def action_view_loyalty_card(self):
        """Open (or create) the Autochapeau loyalty card for this partner."""
        self.ensure_one()
        card = self._get_autochapeau_loyalty_card(create_if_missing=True)
        if not card:
            raise UserError(
                _("No loyalty program is configured. "
                  "Set a loyalty program on the company or create an active loyalty program.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Loyalty Card"),
            "res_model": "loyalty.card",
            "view_mode": "form",
            "res_id": card.id,
            "target": "new",
            "context": {
                "dialog_size": "medium",
                "form_view_initial_mode": "readonly",
            },
        }

    def _get_autochapeau_loyalty_card(self, create_if_missing=True):
        """Return the partner loyalty card, searching DB directly (not stored related)."""
        self.ensure_one()
        partner = self.commercial_partner_id
        Card = self.env["loyalty.card"].sudo()
        card = Card.search(
            [
                ("partner_id", "=", partner.id),
                ("program_id.program_type", "=", "loyalty"),
                ("program_id.active", "=", True),
            ],
            limit=1,
        )
        if card:
            return card
        if not create_if_missing:
            return Card
        program = self.env.company.loyalty_program_id
        if not program:
            program = self.env["loyalty.program"].sudo().search(
                [("program_type", "=", "loyalty"), ("active", "=", True)],
                limit=1,
            )
        if not program:
            return Card
        return Card.with_context(loyalty_no_mail=True, tracking_disable=True).create(
            {
                "program_id": program.id,
                "partner_id": partner.id,
                "points": 0,
            }
        )

    def _get_autochapeau_loyalty_points_for_amount(self, base_amount):
        """Points for amount before discount, using loyalty rule + membership factor."""
        self.ensure_one()
        if base_amount <= 0:
            return 0.0
        partner = self.commercial_partner_id
        card = partner._get_autochapeau_loyalty_card(create_if_missing=False)
        program = card.program_id if card else self.env.company.loyalty_program_id
        if not program:
            program = self.env["loyalty.program"].sudo().search(
                [("program_type", "=", "loyalty"), ("active", "=", True)],
                limit=1,
            )
        rule = program.rule_ids[:1] if program else self.env["loyalty.rule"]
        if rule and rule.reward_point_mode == "money" and rule.reward_point_amount:
            points = rule.reward_point_amount * base_amount
            mode = "money"
        elif rule and rule.reward_point_mode == "order" and rule.reward_point_amount:
            points = rule.reward_point_amount
            mode = "order"
        else:
            points = base_amount / 10.0
            mode = "fallback_/10"

        membership_factor = None
        if (
            not partner.is_company
            and partner.membership_id
            and rule
            and rule.reward_point_amount
        ):
            membership_line = rule.membership_point_ids.filtered(
                lambda mp: mp.membership_id == partner.membership_id
            )[:1]
            if membership_line and membership_line.reward_point_amount > 0:
                membership_factor = (
                    membership_line.reward_point_amount / rule.reward_point_amount
                )
                points *= membership_factor

        result = float_round(points, precision_digits=2, rounding_method="DOWN")
        _logger.critical(
            "[autochapeau_loyalty] points calc partner=%s amount=%s program=%s "
            "rule=%s mode=%s membership=%s factor=%s result=%s",
            partner.id,
            base_amount,
            program.display_name if program else False,
            rule.id if rule else False,
            mode,
            partner.membership_id.display_name if partner.membership_id else False,
            membership_factor,
            result,
        )
        return result
