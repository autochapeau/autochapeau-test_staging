from odoo import api, models
from odoo.tools import float_compare


_DISCOUNT_LIMIT_WATCHED = ("discount", "price_unit", "product_id", "product_uom_qty")


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

    def _sale_discount_limit_is_amount_line(self):
        """Discount button lines: negative price, not a percent on the product line."""
        self.ensure_one()
        if self._sale_discount_limit_skip():
            return False
        discount_product = self.order_id.company_id.sale_discount_product_id
        if discount_product and self.product_id == discount_product:
            return True
        return float_compare(self.price_unit, 0.0, precision_digits=2) < 0

    def _sale_discount_limit_base_amount(self):
        self.ensure_one()
        return (self.price_unit or 0.0) * (self.product_uom_qty or 0.0)

    def _discount_limit_reset_order_approval(self):
        orders = self.mapped("order_id").filtered(
            lambda order: order.state in ("draft", "sent")
        )
        orders._reset_discount_approval()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        if any(
            any(field in vals for field in _DISCOUNT_LIMIT_WATCHED)
            for vals in vals_list
        ):
            lines._discount_limit_reset_order_approval()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field in _DISCOUNT_LIMIT_WATCHED):
            self._discount_limit_reset_order_approval()
        return res

    def unlink(self):
        orders = self.mapped("order_id").filtered(
            lambda order: order.state in ("draft", "sent")
        )
        res = super().unlink()
        orders._reset_discount_approval()
        return res
