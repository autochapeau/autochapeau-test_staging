from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _sale_discount_limit_skip(self):
        """Skip system/loyalty lines that are not manual salesperson discounts."""
        self.ensure_one()
        if self.display_type:
            return True
        if "is_loyalty_redeem_line" in self._fields and self.is_loyalty_redeem_line:
            return True
        return False

    def _check_user_discount_limit(self):
        user = self.env.user
        max_discount = user._get_max_sale_discount_percent()
        for line in self:
            if line._sale_discount_limit_skip():
                continue
            discount = line.discount or 0.0
            if float_compare(discount, 0.0, precision_digits=2) <= 0:
                continue
            if float_compare(discount, max_discount, precision_digits=2) > 0:
                raise ValidationError(_(
                    "You are not allowed to apply a discount higher than "
                    "%(max)s%%.\n"
                    "User: %(user)s\n"
                    "Product: %(product)s\n"
                    "Requested discount: %(discount)s%%",
                    max=max_discount,
                    user=user.display_name,
                    product=line.product_id.display_name or line.display_name,
                    discount=discount,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_user_discount_limit()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "discount" in vals:
            self._check_user_discount_limit()
        return res

    @api.constrains("discount")
    def _constrain_user_discount_limit(self):
        self._check_user_discount_limit()
