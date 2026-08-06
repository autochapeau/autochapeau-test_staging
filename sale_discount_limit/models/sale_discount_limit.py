from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleDiscountLimit(models.Model):
    _name = "sale.discount.limit"
    _description = "Sale Discount Limit"
    _order = "max_discount_percent desc, id"

    name = fields.Char(
        string="Description",
        help="Optional label, e.g. Salespersons 10%.",
    )
    user_ids = fields.Many2many(
        "res.users",
        "sale_discount_limit_user_rel",
        "limit_id",
        "user_id",
        string="Users",
        required=True,
        domain="[('share', '=', False)]",
    )
    max_discount_percent = fields.Float(
        string="Max Discount (%)",
        required=True,
        default=10.0,
        help="Maximum discount percentage these users may apply on sale order lines.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    @api.constrains("max_discount_percent")
    def _check_max_discount_percent(self):
        for rule in self:
            if rule.max_discount_percent < 0 or rule.max_discount_percent > 100:
                raise ValidationError(_(
                    "Max Discount (%) must be between 0 and 100."
                ))

    @api.constrains("user_ids")
    def _check_user_ids(self):
        for rule in self:
            if not rule.user_ids:
                raise ValidationError(_("Please select at least one user."))

    def name_get(self):
        result = []
        for rule in self:
            users = ", ".join(rule.user_ids.mapped("name")[:3])
            if len(rule.user_ids) > 3:
                users = _("%s and others") % users
            label = rule.name or users or _("Discount Limit")
            result.append((
                rule.id,
                "%s (%s%%)" % (label, rule.max_discount_percent),
            ))
        return result
