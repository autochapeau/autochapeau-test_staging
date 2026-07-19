import json

import pytz

from odoo import fields, http
from odoo.http import request
from .common import authorization_required, check_params, make_json_response, make_response

import logging
_logger = logging.getLogger(__name__)


def _date_to_local(naive_dt, user_tz):
    """Convert a naive UTC datetime to user's local datetime without timezone info."""
    biotime_tz = pytz.timezone(user_tz or "UTC")
    ran = pytz.utc.localize(naive_dt).astimezone(biotime_tz)
    return ran.strftime("%Y-%m-%d %H:%M:%S")


class AppointmentAPI(http.Controller):
    @http.route("/v1/appointment_slots", type="http", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_appointment_slots(self):
        """Get appointment slots by branch and return branches list."""
        # Récupération des branches AVANT toute logique métier
        # branches = request.env["hr.department"].sudo().search_read(
        #     [("department_type", "=", "branche")], ["id", "name"])
        try:
            user = request.env["res.users"].sudo().browse(request.uid)
            data = json.loads(request.httprequest.data)
            branch_id = data.get("branch_id")
            fields_name = ["id", "start_date", "finish_date", "is_available"]
            slots = (
                request.env["car.appointment.slot"]
                .sudo()
                .search_read([("department_ids", "in", [branch_id]), ("start_date", ">", fields.Datetime.now())], fields_name)
            )
            # Convert datetime fields to user timezone
            [
                slot.update(
                    {
                        date: _date_to_local(slot[date], user.tz)
                        for date in ["start_date", "finish_date"]
                        if slot.get(date)
                    }
                )
                for slot in slots
            ]
            return make_response(200, slots or [])
        except Exception as e:
            _logger.exception("Something went wrong")
            return make_response(422, {"message": str(e)})

    @http.route("/v1/appointments", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_create_appointment(self):
        # Récupération des branches AVANT toute logique métier
        branches = request.env["hr.department"].sudo().search_read(
            [("department_type", "=", "branche")], ["id", "name"])
        data = json.loads(request.httprequest.data)
        required_keys = ["vehicle_id", "appointment_slot_id", "branch_id"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)

        # Get company_id from appointment_slot
        appointment_slot = request.env["car.appointment.slot"].sudo().browse(
            data.get("appointment_slot_id"))
        company_id = appointment_slot.company_id.id if appointment_slot.company_id else request.env.company.id

        appointment_vals = {
            "vehicle_id": data.get("vehicle_id"),
            "appointment_slot_id": data.get("appointment_slot_id"),
            "branch_id": data.get("branch_id"),
            "company_id": company_id,
            "partner_id": request.env.user.partner_id.id,
            "service_ids": [
                (0, 0, {"product_id": service_id}) for service_id in data.get("service_ids", [])
            ]
        }
        try:
            appointment = request.env["car.appointment"].sudo().create(
                appointment_vals)
        except Exception as e:
            _logger.exception("Something went wrong")
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e), "branches": branches})
        response_data = {
            "message": "success",
            "appointment_id": appointment.id,
            "branches": branches
        }
        return make_json_response(200, response_data)
