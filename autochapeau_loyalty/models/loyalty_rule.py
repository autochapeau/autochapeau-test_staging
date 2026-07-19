from odoo import fields, models


class LoyaltyRule(models.Model):
    _inherit = "loyalty.rule"

    membership_point_ids = fields.One2many(
        "loyalty.rule.membership", "rule_id", string="Points per Membership")


class LoyaltyRuleMembership(models.Model):
    _name = "loyalty.rule.membership"
    _description = "Loyalty Rule Points per Membership Level"

    rule_id = fields.Many2one(
        "loyalty.rule", string="Rule", required=True, ondelete="cascade")
    membership_id = fields.Many2one(
        "customer.membership.level", string="Membership", required=True, ondelete="cascade")
    reward_point_amount = fields.Float(string="Grant", default=1.0)

    _sql_constraints = [("rule_membership_uniq", "unique(rule_id, membership_id)",
                         "A membership can only be configured once per rule.")]
