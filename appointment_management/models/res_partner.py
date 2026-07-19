from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    loyalty_balance = fields.Float(compute="_compute_loyalty", store=True)
    wallet_balance = fields.Float(compute="_compute_loyalty", store=True)
    loyalty_card_id = fields.Many2one("loyalty.card", compute="_compute_loyalty", store=True)
    wallet_card_id = fields.Many2one("loyalty.card", compute="_compute_loyalty", store=True)
    loyalty_card_ids = fields.One2many("loyalty.card", "partner_id")
    loyalty_exchange_log_ids = fields.One2many("loyalty.exchange.log", "partner_id")

    @api.depends("loyalty_card_ids", "loyalty_card_ids.points", "loyalty_card_ids.program_id.active")
    def _compute_loyalty(self):
        for partner in self:
            # loyalty points
            loyalty_cards = partner.loyalty_card_ids.filtered(
                lambda card: card.program_id.active and card.program_id.program_type == "loyalty"
            )
            loyalty_card_id = loyalty_cards and loyalty_cards[0] or False
            partner.loyalty_card_id = loyalty_card_id
            partner.loyalty_balance = loyalty_card_id and loyalty_card_id.points or 0
            # wallet points
            wallet_cards = partner.loyalty_card_ids.filtered(
                lambda card: card.program_id.active and card.program_id.program_type == "ewallet"
            )
            wallet_card_id = wallet_cards and wallet_cards[0] or False
            partner.wallet_card_id = wallet_card_id
            partner.wallet_balance = wallet_card_id and wallet_card_id.points or 0

    def create(self, vals):
        partner = super().create(vals)
        # create loyalty card
        loyalty_obj = self.env["loyalty.card"]
        company_id = self.env.company
        loyalty_obj.sudo().with_context(loyalty_no_mail=True, tracking_disable=True).create(
            {
                "program_id": company_id.loyalty_program_id.id,
                "partner_id": partner.id,
                "points": 0,
            }
        )
        # create eWallet card
        loyalty_obj.sudo().with_context(loyalty_no_mail=True, tracking_disable=True).create(
            {
                "program_id": company_id.wallet_program_id.id,
                "partner_id": partner.id,
                "points": 0,
            }
        )
        return partner

    def exchange_loyalty_points_to_wallet(self, points=0):
        self.ensure_one()
        # use the value of discount in  the first reword in the program linked to partner loyalty card
        if not self.loyalty_card_id:
            raise UserError(_("No Loyalty card found for this customer"))
        reward_id = self.loyalty_card_id.program_id.reward_ids[0]
        exchange_points = points
        if not exchange_points:
            exchange_points = self.loyalty_card_id.points
        if not exchange_points or exchange_points > self.loyalty_card_id.points:
            raise UserError(_("No points to exchange"))
        if not self.wallet_card_id:
            raise UserError(_("No eWallet found for this customer"))
        amount_wallet = exchange_points * (reward_id.discount)
        self.wallet_card_id.points += amount_wallet
        self.loyalty_card_id.points -= exchange_points
        self.loyalty_exchange_log_ids = [
            (
                0,
                0,
                {
                    "type": "loyalty_exchange",
                    "points": points,
                    "amount": amount_wallet,
                    "card_source_id": self.loyalty_card_id.id,
                    "card_destination_id": self.wallet_card_id.id,
                },
            )
        ]


class LoyaltyExchangeLog(models.Model):
    _name = "loyalty.exchange.log"
    _description = "Loyalty card log"

    partner_id = fields.Many2one("res.partner")

    type = fields.Selection(
        [
            ("loyalty_exchange", "Loyalty exchange to Wallet"),
            ("alrajhi_loyalty_exchange", "Alrajhi Loyalty exchange to Wallet"),
            ("qitaf_loyalty_exchange", "Qitaf Loyalty exchange to Wallet"),
            ("yougotagift_loyalty_exchange", "You GotaGift Loyalty exchange to Wallet"),
            ("mylist_loyalty_exchange", "MyList Loyalty exchange to Wallet"),
            ("payment_by_wallet", "Payment by Wallet"),
        ]
    )
    card_source_id = fields.Many2one("loyalty.card")
    card_destination_id = fields.Many2one("loyalty.card")
    points = fields.Float(required=True)
    amount = fields.Float()
    order_id = fields.Many2one(comodel_name="sale.order", ondelete="cascade")
