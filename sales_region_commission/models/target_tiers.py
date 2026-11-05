from dateutil.relativedelta import relativedelta

from odoo import _, api, Command, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_round


class Target(models.Model):
    _inherit = "sales.commission.target"
    _description = "Sales target period"

    period_type = fields.Selection([("month", "Monthly"), ("quarter", "Quarterly"),
        ("half", "Half-yearly"), ("year", "Yearly")], required=True, default="month")
    date_end = fields.Date(compute="_compute_date_end", store=True)
    member_target_ids = fields.One2many("sales.commission.target.member", "target_id", copy=False)

    @api.depends("month", "period_type")
    def _compute_date_end(self):
        lengths = {"month": 1, "quarter": 3, "half": 6, "year": 12}
        for target in self:
            target.date_end = target.month + relativedelta(months=lengths[target.period_type], days=-1) if target.month else False

    @api.onchange("period_type")
    def _onchange_period_type(self):
        lengths = {"month": 1, "quarter": 3, "half": 6, "year": 12}
        for target in self:
            if target.month:
                length = lengths[target.period_type]
                target.month = target.month.replace(day=1, month=((target.month.month - 1) // length) * length + 1)

    @api.constrains("month", "period_type", "team_id", "company_id", "date_end")
    def _check_period_overlap(self):
        for target in self:
            self.env.cr.execute("UPDATE crm_team SET write_date=write_date WHERE id=%s", [target.team_id.id])
            starts = {"month": range(1, 13), "quarter": (1, 4, 7, 10), "half": (1, 7), "year": (1,)}
            if target.month.month not in starts[target.period_type]:
                raise ValidationError(_("Start the target on the first month of its calendar period."))
            if self.sudo().search_count([("id", "!=", target.id), ("team_id", "=", target.team_id.id),
                ("company_id", "=", target.company_id.id), ("month", "<=", target.date_end), ("date_end", ">=", target.month)]):
                raise ValidationError(_("Target periods for the same team must not overlap."))

    def action_distribute_members(self):
        self.check_access_rights("write")
        self.check_access_rule("write")
        for target in self:
            users = (target.team_id.member_ids | target.team_id.user_id | target.team_id.commission_manager_id).filtered(
                lambda user: user.active and target.company_id in user.company_ids)
            if not users:
                raise ValidationError(_("Add active team members or a team manager before distributing the target."))
            users = users.sorted("id")
            share = target.currency_id.round(target.amount / len(users))
            commands = [Command.clear()]
            remaining = target.amount
            for index, user in enumerate(users):
                amount = target.currency_id.round(remaining if index == len(users) - 1 else share)
                remaining -= amount
                commands.append(Command.create({"user_id": user.id, "amount": amount}))
            target.write({"member_target_ids": commands})
        return True


class MemberTarget(models.Model):
    _name = "sales.commission.target.member"
    _description = "Individual share of team target"
    _check_company_auto = True

    target_id = fields.Many2one("sales.commission.target", required=True, ondelete="cascade", check_company=True)
    company_id = fields.Many2one(related="target_id.company_id", store=True)
    currency_id = fields.Many2one(related="target_id.currency_id")
    team_id = fields.Many2one(related="target_id.team_id", store=True)
    user_id = fields.Many2one("res.users", required=True, check_company=True)
    amount = fields.Monetary(required=True)
    _sql_constraints = [("target_user_unique", "unique(target_id, user_id)", "A member can have only one share per target.")]

    @api.constrains("amount", "user_id", "target_id")
    def _check_share(self):
        for share in self:
            if share.amount < 0:
                raise ValidationError(_("An individual target cannot be negative."))
            users = share.team_id.member_ids | share.team_id.user_id | share.team_id.commission_manager_id
            if share.user_id not in users:
                raise ValidationError(_("Allocate the target to a team member or manager."))


class Tier(models.Model):
    _name = "sales.commission.tier"
    _description = "Commission rate by target achievement"
    _order = "achievement_from, id"

    rule_id = fields.Many2one("sales.commission.rule", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="rule_id.company_id", store=True)
    achievement_from = fields.Float(string="Achievement From %", digits=(16, 2), required=True)
    achievement_to = fields.Float(string="Achievement To %", digits=(16, 2), help="Zero means no upper limit.")
    rate = fields.Float(string="Commission %", digits=(16, 4), required=True)

    @api.constrains("rule_id", "achievement_from", "achievement_to", "rate")
    def _check_tier(self):
        for tier in self:
            if tier.achievement_from < 0 or (tier.achievement_to and tier.achievement_to < tier.achievement_from) or not 0 <= tier.rate <= 100:
                raise ValidationError(_("Use non-negative achievement bounds and a commission rate between 0 and 100."))
            others = tier.rule_id.sudo().tier_ids - tier
            upper = tier.achievement_to or float("inf")
            if any(tier.achievement_from <= (other.achievement_to or float("inf")) and other.achievement_from <= upper for other in others):
                raise ValidationError(_("Achievement tiers within a rule must not overlap."))


class Rule(models.Model):
    _inherit = "sales.commission.rule"

    tier_ids = fields.One2many("sales.commission.tier", "rule_id", copy=True)
    apply_discount_adjustment = fields.Boolean(string="Apply Customer Discount Adjustment",
        help="0% discount increases commission by 20%; 1–10% leaves it unchanged; 10.01–20% reduces it by 25%. Other discounts require review.")
    personal_target = fields.Monetary(compute="_compute_personal_target", currency_field="currency_id")
    currency_id = fields.Many2one(related="company_id.currency_id")

    @api.depends("user_id", "company_id")
    def _compute_personal_target(self):
        today = fields.Date.context_today(self)
        for rule in self:
            shares = self.env["sales.commission.target.member"].search([
                ("user_id", "=", rule.user_id.id), ("company_id", "=", rule.company_id.id),
                ("target_id.month", "<=", today), ("target_id.date_end", ">=", today)])
            rule.personal_target = sum(shares.mapped("amount"))

    def _rate_for_invoice_line(self, line, team, date):
        self.ensure_one()
        rate = self.rate
        achievement, personal_target = 0, 0
        if self.tier_ids:
            shares = self.env["sales.commission.target.member"].sudo().search([
                ("user_id", "=", self.user_id.id), ("team_id", "=", team.id), ("company_id", "=", self.company_id.id),
                ("target_id.month", "<=", date), ("target_id.date_end", ">=", date)])
            if len(shares) != 1 or shares.amount <= 0:
                return False, 0, 0, _("A tiered rule needs one positive individual target for this team and invoice date.")
            target = shares.target_id
            if not target.currency_id.is_zero(sum(target.member_target_ids.mapped("amount")) - target.amount):
                return False, 0, 0, _("Individual target shares must add up to the team target.")
            # Updating the locked row also makes concurrent repeatable-read sessions retry.
            self.env.cr.execute("UPDATE sales_commission_target SET write_date=write_date WHERE id=%s", [target.id])
            lines = self.env["account.move.line"].sudo().search([
                ("company_id", "=", self.company_id.id), ("parent_state", "=", "posted"),
                ("move_id.move_type", "in", ["out_invoice", "out_refund"]), ("display_type", "=", "product"),
                ("is_downpayment", "=", False), ("invoice_date", ">=", target.month), ("invoice_date", "<=", target.date_end),
                ("sale_line_ids.order_id.user_id", "=", self.user_id.id), ("sale_line_ids.order_id.team_id", "=", team.id)])
            lines = lines.filtered(lambda item: not getattr(item, "is_service_advance", False)
                and item.sale_line_ids.order_id.user_id == self.user_id and item.sale_line_ids.order_id.team_id == team)
            personal_target = shares.amount
            achievement = float_round(-sum(lines.mapped("balance")) / personal_target * 100, precision_digits=2)
            tiers = self.tier_ids.filtered(lambda tier: tier.achievement_from <= achievement
                and (not tier.achievement_to or achievement <= tier.achievement_to))
            rate = tiers.rate if len(tiers) == 1 else 0
        if self.apply_discount_adjustment:
            discount = float_round(line.discount, precision_digits=2)
            if discount == 0:
                rate *= 1.2
            elif 1 <= discount <= 10:
                pass
            elif 10.01 <= discount <= 20:
                rate *= .75
            else:
                return False, achievement, personal_target, _("Customer discount is outside the configured adjustment bands; review the commission.")
        return rate, achievement, personal_target, False


class Entry(models.Model):
    _inherit = "sales.commission.entry"

    achievement_percent = fields.Float(readonly=True, digits=(16, 2))
    personal_target = fields.Monetary(readonly=True)
