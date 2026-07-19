import json

from odoo import http
from odoo.http import request

from .common import check_params, check_request_body, make_json_response


class LoginApi(http.Controller):
    @http.route("/v1/login", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @check_request_body
    def v1_api_login(self):
        """This endpoint is used to log in with user credentials.And return the key will be used in other api key."""
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["login", "password"])
        if check_data:
            return make_json_response(422, check_data)
        login_input = data.get("login")
        password = data.get("password")

        try:
            user = None
            if "@" in login_input:
                user = request.env["res.users"].sudo().search([("email", "=", login_input)], limit=1)
            elif login_input.isdigit():
                user = request.env["res.users"].sudo().search([("phone", "=", login_input)], limit=1)

            if not user:
                return make_json_response(
                    401, {"message": "معلومات الدخول غير صحيحة. يرجى التأكد من إدخال المعلومات الصحيحة."}
                )

            uid = request.session.authenticate(request.env.cr.dbname, user.login, password)
            api_keys_obj = request.env["res.users.apikeys"].with_user(uid)
            key = api_keys_obj._generate("api", "api for website")
            return make_json_response(200, {"api_key": key, "user_id": user.id})

        except Exception as e:
            return make_json_response(500, {"message": e})
