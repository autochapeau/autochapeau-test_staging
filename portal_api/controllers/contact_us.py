import json

from odoo import SUPERUSER_ID, http
from odoo.http import request

from .common import check_params, check_request_body, make_json_response


class ContactUs(http.Controller):
    @http.route("/v1/contactus", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @check_request_body
    def v1_api_contactus(self):
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["name", "email_from", "subject", "description"])
        if check_data:
            return make_json_response(422, check_data)
        try:
            values = {
                "contact_name": data.get("name"),
                "phone": data.get("phone"),
                "email_from": data.get("email_from"),
                "partner_name": data.get("partner_name"),
                "name": data.get("subject"),
                "description": data.get("description"),
            }
            request.env["crm.lead"].with_user(SUPERUSER_ID).create(values)
            return make_json_response(200, "Lead created successfully")
        except Exception as e:
            return make_json_response(500, {"message": e})
