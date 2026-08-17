from odoo import models
from odoo.tools import format_amount


class LoyaltyCard(models.Model):
    _inherit = "loyalty.card"

    def _format_points(self, points):
        """Avoid crash when program has no currency (e.g. archived cards)."""
        self.ensure_one()
        currency = self.program_id.currency_id
        if currency and self.point_name == currency.symbol:
            return format_amount(self.env, points, currency)
        if points == int(points):
            return f"{int(points)} {self.point_name or ''}"
        return f"{points:.2f} {self.point_name or ''}"
