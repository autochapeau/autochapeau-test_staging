from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def create_from_ui(self, partner):
        """Customers created from POS are always Internal."""
        partner_id = partner.get("id")
        if not partner_id:
            partner = dict(partner)
            partner["partner_type"] = "internal"
        return super().create_from_ui(partner)
