import json

from odoo import http
from odoo.http import request

from .common import authorization_required, check_params, format_search_read_result, make_json_response, make_response


class VehicleAPI(http.Controller):
    @http.route("/v1/models", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    def v1_get_models(self):
        try:
            fields_name = ["id", "display_name", "brand_id"]
            brand_id = request.env.ref("cars_management.unknown_manufacturer").id
            models = request.env["fleet.vehicle.model"].sudo().search_read([("brand_id", "!=", brand_id)], fields_name)
            result = format_search_read_result(models, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/brands", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    def v1_get_brands(self):
        try:
            fields_name = ["id", "name"]
            brands = request.env["fleet.vehicle.model.brand"].sudo().search_read([], fields_name)
            result = format_search_read_result(brands, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/vehicles", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_create_vehicle(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["title", "vin_sn", "plate_numbers"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        if not data.get("model_id") and not data.get("unverified_model_name"):
            return make_json_response(422, "You have to add either field 'model_id' or field 'unverified_model_name'")
        vehicle_vals = {
            "partner_id": request.env.user.partner_id.id,
            "model_id": data.get("model_id"),
            "unverified_model_name": data.get("unverified_model_name"),
            "vin_sn": data["vin_sn"],
            "plate_letters": data["plate_letters"],
            "plate_letters_ar": data["plate_letters_ar"],
            "plate_numbers": data["plate_numbers"],
            "plate_numbers_ar": data["plate_numbers_ar"],
            "title": data["title"],
        }
        try:
            vehicle = request.env["fleet.vehicle"].sudo().create(vehicle_vals)
        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e)})
        response_data = {"message": "success", "vehicle_id": vehicle.id}
        return make_json_response(200, response_data)

    @http.route("/v1/vehicles/edit", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_edit_vehicles(self):
        # all fields should be required except image_1920
        data = json.loads(request.httprequest.data)
        required_keys = ["vehicle_id", "title", "vin_sn", "plate_numbers"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        try:
            vehicle = request.env["fleet.vehicle"].sudo().browse(data.get("vehicle_id"))
            data.pop("vehicle_id")
            vehicle.sudo().write(data)
            response_data = {"message": "Vehicle has been modified successfully."}
            return make_json_response(200, response_data)
        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e)})
