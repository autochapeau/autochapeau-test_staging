from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    sale_max_discount_percent = fields.Float(
        string="Max Sale Discount (%)",
        compute="_compute_sale_max_discount_percent",
        help="Highest max discount configured for this user. 0 means no discount allowed.",
    )

    @api.depends_context("company")
    def _compute_sale_max_discount_percent(self):
        Limit = self.env["sale.discount.limit"].sudo()
        for user in self:
            user.sale_max_discount_percent = user._get_max_sale_discount_percent()

    def _get_max_sale_discount_percent(self):
        """Return the highest active discount limit for this user (0 if none)."""
        self.ensure_one()
        domain = [
            ("active", "=", True),
            ("user_ids", "in", self.id),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.env.company.id),
        ]
        rules = self.env["sale.discount.limit"].sudo().search(domain)
        if not rules:
            return 0.0
        return max(rules.mapped("max_discount_percent") or [0.0])
