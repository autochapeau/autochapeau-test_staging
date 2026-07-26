from odoo import http
from odoo.http import request


class PosAppointmentController(http.Controller):

    @http.route("/pos_appointment/new", type="http", auth="user")
    def new_appointment(self, partner_id=0, vehicle_id=0, pos_uid="", pos_order_id=0, **kwargs):
        """Open appointment form; defaults come from session (see car.appointment.default_get)."""
        request.session["pos_appointment_default_partner_id"] = int(partner_id or 0) or False
        request.session["pos_appointment_default_vehicle_id"] = int(vehicle_id or 0) or False
        request.session["pos_appointment_pos_uid"] = pos_uid or False
        request.session["pos_appointment_pos_order_id"] = int(pos_order_id or 0) or False
        action = request.env.ref("pos_appointment.action_new_appointment_from_pos")
        return request.redirect(
            f"/web#action={action.id}&model=car.appointment&view_type=form"
        )
