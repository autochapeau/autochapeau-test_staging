import json
import uuid
from base64 import b64encode
from datetime import datetime

import pytz
import requests

from odoo import http
from odoo.http import request
from odoo.tools.misc import file_path

from .common import authorization_required, check_params, make_json_response


class QitafLoyaltyAPI(http.Controller):
    @http.route("/v1/qitaf/loyalty/otp", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_qitaf_loyalty_otp(self):
        data = json.loads(request.httprequest.data)
        if data.get("phone"):
            # Send OTP request
            response = self.generate_redemption_otp(phone=self.parse_phone(data.get("phone")))
            if response.get("success"):
                response_data = {"message": "Success"}
                return make_json_response(200, response_data)
            else:
                response_error = ""
                if response.get("error"):
                    response_error = response.get("error")[0]
                    if response_error.get("code"):
                        response_error["code"] = int(response_error.get("code"))
                return make_json_response(response.get("status_code", 422), {"message": response_error})

    @http.route("/v1/qitaf/loyalty/redeem", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_qitaf_loyalty_redeem(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["phone", "otp", "amount"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        response = self.redeem_qitaf_points(
            phone=self.parse_phone(data.get("phone")), otp=data.get("otp"), amount=data.get("amount")
        )
        if response.get("success"):
            partner = request.env.user.partner_id.sudo()
            # Amount comes in negative value
            points_amount = float(data.get("amount"))
            partner.wallet_card_id.points += points_amount
            partner.loyalty_exchange_log_ids = [
                (
                    0,
                    0,
                    {
                        "type": "qitaf_loyalty_exchange",
                        "points": points_amount,
                        "amount": data.get("amount"),
                        "card_destination_id": partner.wallet_card_id.id,
                    },
                )
            ]
            response_data = {"message": "Success"}
            return make_json_response(200, response_data)
        else:
            response_error = ""
            if response.get("error"):
                response_error = response.get("error")[0]
                if response_error.get("code"):
                    response_error["code"] = int(response_error.get("code"))
            return make_json_response(response.get("status_code", 422), {"message": response_error})

    @http.route("/v1/qitaf/loyalty/reward", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_qitaf_loyalty_reward(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["phone", "amount"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        endpoint = "/api/v1/earn/reward"
        qitaf_branch_id = request.env["ir.config_parameter"].sudo().get_param("qitaf_branch_id")
        qitaf_terminal_id = request.env["ir.config_parameter"].sudo().get_param("qitaf_terminal_id")
        mobile = self.parse_phone(data.get("phone"))
        amount = data.get("amount")
        payload = {
            "Amount": amount,
            "RequestDate": self.get_current_request_date(),
            "Msisdn": mobile,
            "BranchId": qitaf_branch_id,
            "TerminalId": qitaf_terminal_id,
        }
        response = self.http_post(endpoint, headers=self.get_default_headers(), json=payload)
        if response.get("success"):
            response_data = {"message": "Success", "reward_data": response.get("data")}
            return make_json_response(200, response_data)
        else:
            response_error = ""
            if response.get("error"):
                response_error = response.get("error")[0]
                if response_error.get("code"):
                    response_error["code"] = int(response_error.get("code"))
            return make_json_response(response.get("status_code", 422), {"message": response_error})

    ##########################
    # Qitaf Helper functions #
    ##########################

    def parse_phone(self, number):
        if number.startswith("966") and len(number) == 12:
            return "0" + number[3:]
        return number

    def get_current_request_date(self):
        ksa_timezone = pytz.timezone("Asia/Riyadh")  # KSA timezone
        return datetime.now(ksa_timezone).strftime("%Y-%m-%dT%H:%M:%S")  # ISO 8601 format without microseconds

    def parse_response(self, response):
        try:
            data = response.json()
        except ValueError:
            data = {"error": "Invalid JSON response", "status_code": response.status_code}

        if response.ok:
            return {"success": True, "data": data}
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "error": data.get("errors", data) if isinstance(data, dict) else str(data),
            }

    def http_post(self, endpoint, headers=None, data=None, json=None):
        BASE_URL = request.env["ir.config_parameter"].sudo().get_param("qitaf_loyalty_url")
        client_cert = file_path("portal_api/static/src/certs/qitaf_client_cert.pem")
        client_key = file_path("portal_api/static/src/certs/qitaf_client_key.key")
        ca_cert = file_path("portal_api/static/src/certs/qitaf-ca-chain.crt")
        response = requests.post(
            f"{BASE_URL}{endpoint}",
            cert=(client_cert, client_key),
            verify=ca_cert,
            headers=headers,
            data=data,
            json=json,
            timeout=15,
        )
        return self.parse_response(response)

    def get_default_headers(self):
        qitaf_loyalty_token = request.env["ir.config_parameter"].sudo().get_param("qitaf_loyalty_token")
        qitaf_username = request.env["ir.config_parameter"].sudo().get_param("qitaf_username")
        qitaf_password = request.env["ir.config_parameter"].sudo().get_param("qitaf_password")
        auth_token = b64encode(f"{qitaf_username}:{qitaf_password}".encode()).decode("ascii")

        default_headers = {
            "Accept-Language": "en-US",
            "GlobalId": str(uuid.uuid4()),
            "X-Secret-Token": qitaf_loyalty_token,
            "Authorization": f"Basic {auth_token}",
        }
        return default_headers

    # API Function: Generate redemption OTP
    def generate_redemption_otp(self, api_version=1, phone=None):
        endpoint = f"/api/v{api_version}/redemption/otp"
        qitaf_branch_id = request.env["ir.config_parameter"].sudo().get_param("qitaf_branch_id")
        qitaf_terminal_id = request.env["ir.config_parameter"].sudo().get_param("qitaf_terminal_id")
        payload = {
            "Msisdn": phone,
            "BranchId": qitaf_branch_id,
            "TerminalId": qitaf_terminal_id,
            "RequestDate": self.get_current_request_date(),
        }
        return self.http_post(endpoint, headers=self.get_default_headers(), json=payload)

    # API Function: Redeem Qitaf points
    def redeem_qitaf_points(self, phone, otp, amount, api_version=1):
        endpoint = f"/api/v{api_version}/redemption/redeem"
        qitaf_branch_id = request.env["ir.config_parameter"].sudo().get_param("qitaf_branch_id")
        qitaf_terminal_id = request.env["ir.config_parameter"].sudo().get_param("qitaf_terminal_id")
        payload = {
            "PIN": otp,
            "Amount": amount,
            "RequestDate": self.get_current_request_date(),
            "Msisdn": phone,
            "BranchId": qitaf_branch_id,
            "TerminalId": qitaf_terminal_id,
        }
        return self.http_post(endpoint, headers=self.get_default_headers(), json=payload)
