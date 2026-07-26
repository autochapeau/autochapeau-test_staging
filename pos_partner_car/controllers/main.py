from odoo import http
from odoo.http import request


class PosPartnerCarController(http.Controller):

    @http.route("/pos_partner_car/new_vehicle", type="http", auth="user")
    def new_vehicle(self, partner_id=0, **kwargs):
        """Open Cars management form; Owner is filled via session in default_get."""
        partner_id = int(partner_id or 0)
        request.session["pos_partner_car_default_partner_id"] = partner_id or False
        action = request.env.ref("pos_partner_car.action_new_vehicle_from_pos")
        return request.redirect(
            f"/web#action={action.id}&model=fleet.vehicle&view_type=form"
        )
