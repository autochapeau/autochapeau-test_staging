from odoo import api, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    @api.model
    def get_pos_partner_vehicles(self, partner_id):
        """Return cars of a partner for POS selection popup."""
        if not partner_id:
            return []
        return self.search_read(
            [("partner_id", "=", partner_id)],
            ["id", "display_name", "license_plate", "size"],
            order="id desc",
        )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        partner_id = self._consume_pos_default_partner_id()
        if not partner_id:
            return res

        partner = self.env["res.partner"].browse(partner_id).exists()
        if not partner:
            return res

        # Always set — web client will keep relevant keys
        res["partner_id"] = partner.id
        res["owner_type"] = "individual"
        res["car_owner_name"] = partner.name or False
        res["car_owner_mobile"] = partner.mobile or partner.phone or False
        res["car_owner_email"] = partner.email or False
        return res

    @api.model
    def _consume_pos_default_partner_id(self):
        """Read partner id stored by POS New-car route (keep until create/cancel)."""
        try:
            from odoo.http import request

            if not request or not hasattr(request, "session"):
                return False
            # Keep value for possible multiple default_get calls on form load
            partner_id = request.session.get("pos_partner_car_default_partner_id") or False
            return int(partner_id) if partner_id else False
        except Exception:
            return False

    @api.model
    def _clear_pos_default_partner_id(self):
        try:
            from odoo.http import request

            if request and hasattr(request, "session"):
                request.session.pop("pos_partner_car_default_partner_id", None)
        except Exception:
            pass

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._clear_pos_default_partner_id()
        return records
