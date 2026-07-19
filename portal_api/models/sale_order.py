from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _add_points_for_coupon(self, coupon_points):
        """Whe have 3 loyalty_type : autochapeau, alrajhi, qitaf
        we should add points to partner only if loyalty_type == autochapeau.
        Loyalty points are granted to individual customers only, not companies.
        """
        if self.env.context.get("bypass_point_changes"):
            return False
        if self.partner_id.is_company:
            return False
        return super()._add_points_for_coupon(coupon_points)

    def _remove_coupon(self, coupon_code=None):
        self.ensure_one()
        if coupon_code:
            # Delete applied coupons matching the code
            matching_coupons = self.applied_coupon_ids.filtered(lambda coupon: coupon.code == coupon_code)
            # Unlink reward lines that use these coupons
            reward_lines = self.order_line.filtered(lambda line: line.coupon_id in matching_coupons)
            reward_lines.unlink()
            matching_coupons.unlink()
        else:
            # No code, we delete everything
            self.applied_coupon_ids.unlink()
            reward_lines = self.order_line.filtered(lambda line: line.reward_id)
            reward_lines.unlink()
