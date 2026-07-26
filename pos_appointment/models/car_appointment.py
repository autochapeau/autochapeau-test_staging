from odoo import api, fields, models


class CarAppointment(models.Model):
    _inherit = "car.appointment"

    pos_order_id = fields.Many2one(
        "pos.order",
        string="POS Order",
        copy=False,
        index=True,
    )
    pos_uid = fields.Char(
        string="POS Order UID",
        copy=False,
        index=True,
        help="POS order reference used to link the appointment before/after the order is synced.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        defaults = self._get_pos_appointment_defaults()
        if not defaults:
            return res

        partner_id = defaults.get("partner_id")
        vehicle_id = defaults.get("vehicle_id")
        pos_uid = defaults.get("pos_uid")
        pos_order_id = defaults.get("pos_order_id")

        if partner_id and ("partner_id" in fields_list or not fields_list):
            res["partner_id"] = partner_id
        if vehicle_id and ("vehicle_id" in fields_list or not fields_list):
            res["vehicle_id"] = vehicle_id
        if pos_uid and ("pos_uid" in fields_list or not fields_list):
            res["pos_uid"] = pos_uid
        if pos_order_id and ("pos_order_id" in fields_list or not fields_list):
            res["pos_order_id"] = pos_order_id
        return res

    @api.model
    def _get_pos_appointment_defaults(self):
        try:
            from odoo.http import request

            if not request or not hasattr(request, "session"):
                return {}
            partner_id = request.session.get("pos_appointment_default_partner_id") or False
            vehicle_id = request.session.get("pos_appointment_default_vehicle_id") or False
            pos_uid = request.session.get("pos_appointment_pos_uid") or False
            pos_order_id = request.session.get("pos_appointment_pos_order_id") or False
            if not any([partner_id, vehicle_id, pos_uid, pos_order_id]):
                return {}
            return {
                "partner_id": int(partner_id) if partner_id else False,
                "vehicle_id": int(vehicle_id) if vehicle_id else False,
                "pos_uid": pos_uid or False,
                "pos_order_id": int(pos_order_id) if pos_order_id else False,
            }
        except Exception:
            return {}

    @api.model
    def _clear_pos_appointment_defaults(self):
        try:
            from odoo.http import request

            if request and hasattr(request, "session"):
                for key in (
                    "pos_appointment_default_partner_id",
                    "pos_appointment_default_vehicle_id",
                    "pos_appointment_pos_uid",
                    "pos_appointment_pos_order_id",
                ):
                    request.session.pop(key, None)
        except Exception:
            pass

    @api.model
    def create(self, vals):
        # Keep same create signature as appointment_management
        defaults = self._get_pos_appointment_defaults()
        if defaults:
            vals.setdefault("partner_id", defaults.get("partner_id") or False)
            vals.setdefault("vehicle_id", defaults.get("vehicle_id") or False)
            vals.setdefault("pos_uid", defaults.get("pos_uid") or False)
            vals.setdefault("pos_order_id", defaults.get("pos_order_id") or False)

        if vals.get("pos_uid") and not vals.get("pos_order_id"):
            pos_order = self.env["pos.order"].search(
                [("pos_reference", "=", vals["pos_uid"])],
                limit=1,
            )
            if pos_order:
                vals["pos_order_id"] = pos_order.id

        appointment = super().create(vals)
        if appointment.pos_order_id and not appointment.pos_order_id.appointment_id:
            appointment.pos_order_id.sudo().write({"appointment_id": appointment.id})
        self._clear_pos_appointment_defaults()
        return appointment

    @api.model
    def get_appointment_for_pos_uid(self, pos_uid):
        """Used by POS after closing the booking tab."""
        if not pos_uid:
            return False
        appointment = self.search([("pos_uid", "=", pos_uid)], limit=1, order="id desc")
        if not appointment:
            return False
        return {
            "id": appointment.id,
            "name": appointment.name or "",
            "state": appointment.state,
        }
