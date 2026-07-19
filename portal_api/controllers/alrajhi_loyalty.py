import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from odoo import http
from odoo.http import request
from odoo.tools.misc import file_path

from .common import authorization_required, check_params, make_json_response


class AlrajhiLoyaltyAPI(http.Controller):
    @http.route("/v1/alrajhi/loyalty/otp", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_alrajhi_loyalty_otp(self):
        data = json.loads(request.httprequest.data)
        if data.get("phone"):
            # Send OTP request
            base_url = request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_url")
            oauth_token = request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_oauth_token")
            merchant_token = request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_merchant_token")
            client_id = request.env["ir.config_parameter"].sudo().get_param("alrajhi.client_id")
            client_secret = request.env["ir.config_parameter"].sudo().get_param("alrajhi.client_secret")
            alrajhi_vals = {"mobile": data.get("phone"), "currency": "SAR", "lang": "en", "mappingPosID": "1001"}
            url = f"{base_url}/api-factory/prod/blu-loyalty/1.0.0/customer-authorization"
            headers = {
                "Authorization": "Bearer " + oauth_token,
                "merchantToken": merchant_token,
                "Content-Type": "application/json",
            }
            try:
                oauth_token_expire_date = (
                    request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_oauth_token_expire_date")
                )
                oauth_token_expire_date = datetime.strptime(oauth_token_expire_date, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > oauth_token_expire_date:
                    # Generate Oauth token
                    token_vals = {
                        "grant_type": "client_credentials",
                        "scope": "customer-authorization otp-validation redemption-transaction-reversal redemption-transactions",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    }
                    token_hearder = {"Content-Type": "application/x-www-form-urlencoded"}
                    token_url = f"{base_url}/api-factory/prod/loyalty-redemption/oauth2/token"
                    token_response = requests.post(token_url, data=token_vals, headers=token_hearder, timeout=15)
                    token_response_content = json.loads(token_response.content)
                    if not token_response.ok:
                        return make_json_response(422, {"message": token_response_content})
                    request.env["ir.config_parameter"].sudo().set_param(
                        "alrajhi_loyalty_oauth_token", token_response_content.get("access_token")
                    )
                    expire_duration = token_response_content.get("token_response_content", 3600)
                    expire_date = datetime.now() + timedelta(seconds=int(expire_duration))
                    request.env["ir.config_parameter"].sudo().set_param(
                        "alrajhi_loyalty_oauth_token_expire_date", expire_date.strftime("%Y-%m-%d %H:%M:%S")
                    )
                    # Update the headers
                    headers["Authorization"] = "Bearer " + token_response_content.get("access_token")
                response = requests.post(url, json=alrajhi_vals, headers=headers, timeout=15)
            except Exception as e:
                request.env.cr.rollback()
                return make_json_response(422, {"message": str(e)})
            response = json.loads(response.content)
            if response.get("otp"):
                response_data = {"otp_token": response.get("otp").get("otp_token")}
                return make_json_response(200, response_data)
            elif response.get("errorCode"):
                message_response = {"code": int(response.get("errorCode")), "description": response.get("message")}
                return make_json_response(422, {"message": message_response})
            elif response.get("httpCode"):
                message_response = {
                    "code": int(response.get("httpCode")),
                    "description": response.get("moreInformation"),
                }
                return make_json_response(422, {"message": message_response})

    @http.route(
        "/v1/alrajhi/loyalty/redeem", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*"
    )
    @authorization_required
    def v1_alrajhi_loyalty_redeem(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["OTPValue", "OTPToken", "amount"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)

        base_url = request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_url")
        oauth_token = request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_oauth_token")
        merchant_token = request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_merchant_token")

        url = f"{base_url}/api-factory/prod/blu-loyalty/1.0.0/otp-validation"
        headers = {
            "Authorization": "Bearer " + oauth_token,
            "merchantToken": merchant_token,
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, json=data, headers=headers, timeout=15)
        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e)})
        response = json.loads(response.content)
        if response.get("message") == "Success":
            partner = request.env.user.partner_id.sudo()
            # Amount comes in negative value
            points_amount = response.get("pointsAmount", 0) * (-1)
            partner.wallet_card_id.points += float(data.get("amount"))
            partner.loyalty_exchange_log_ids = [
                (
                    0,
                    0,
                    {
                        "type": "alrajhi_loyalty_exchange",
                        "points": points_amount,
                        "amount": data.get("amount"),
                        "card_destination_id": partner.wallet_card_id.id,
                    },
                )
            ]
            response_data = {"message": "Success"}
            return make_json_response(200, response_data)
        elif response.get("errorCode"):
            message_response = {"code": int(response.get("errorCode")), "description": response.get("message")}
            return make_json_response(422, {"message": message_response})
        elif response.get("httpCode"):
            message_response = {"code": int(response.get("httpCode")), "description": response.get("moreInformation")}
            return make_json_response(422, {"message": message_response})

    # --------------------------------------------------------
    #
    # ------------------------------------------------------------

    def generate_alrajhi_reward_token(self):
        base_url = request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_url")
        client_id = request.env["ir.config_parameter"].sudo().get_param("alrajhi.client_id")
        client_secret = request.env["ir.config_parameter"].sudo().get_param("alrajhi.client_secret")
        token_vals = {
            "grant_type": "client_credentials",
            "scope": "earn-by-sar earn-by-points earn-by-sar-and-ratio refund-earn-by-sar get-earn-trans-details get-earn-recon",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        token_hearder = {"Content-Type": "application/x-www-form-urlencoded"}
        token_url = f"{base_url}/api-factory/prod/loyalty-accruals/oauth2/token"
        token_response = requests.post(token_url, data=token_vals, headers=token_hearder, timeout=15)
        token_response_content = json.loads(token_response.content)
        if not token_response.ok:
            return False
        return token_response_content.get("access_token")

    @http.route(
        "/v1/alrajhi/loyalty/reward", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*"
    )
    @authorization_required
    def v1_alrajhi_loyalty_reward(self):
        def sign_data(hashed_data, private_key):
            return private_key.sign(hashed_data, padding.PKCS1v15(), hashes.SHA256())

        data = json.loads(request.httprequest.data)
        required_keys = ["amount", "phone", "branch_code"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)

        base_url = request.env["ir.config_parameter"].sudo().get_param("alrajhi_loyalty_url")
        partner_code = request.env["ir.config_parameter"].sudo().get_param("alrajhi_reward.partnerCode")
        location_code = request.env["ir.config_parameter"].sudo().get_param("alrajhi_reward.locationCode")
        location_code_dmm = request.env["ir.config_parameter"].sudo().get_param("alrajhi_reward.locationCodeDMM")
        location_code_kho = request.env["ir.config_parameter"].sudo().get_param("alrajhi_reward.locationCodeKHO")
        transaction_number = str(uuid.uuid4())
        current_date = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        mobile = data.get("phone")
        amount = data.get("amount")
        branch_code = data.get("branch_code") or location_code or location_code_dmm or location_code_kho
        # --- Step 1: Define the payload ---
        payload = {
            "partnerCode": partner_code,
            "locationCode": branch_code,
            "saleTrnNo": transaction_number,
            "date": current_date,
            "mobile": mobile,
            "amount": amount,
        }
        # --- Step 2: Serialize payload in canonical form ---
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        # --- Step 3: Load private key from PEM file ---
        private_key = file_path("portal_api/static/src/alrajhi/privateKey.pem")
        with open(private_key, "rb") as key_file:
            private_key = load_pem_private_key(key_file.read(), password=None)
        # --- Step 4: Sign the hash ---
        signed_hash = sign_data(payload_bytes, private_key)
        # --- Step 6: Encode signature in base64 ---
        signature_base64 = base64.b64encode(signed_hash).decode("utf-8")
        # 7 : send request
        oauth_token = self.generate_alrajhi_reward_token()
        url = f"{base_url}/api-factory/prod/loyalty-accruals/1.0.0/earn-by-sar"
        headers = {
            "Authorization": "Bearer " + oauth_token,
            "x-signature": signature_base64,
            "Content-Type": "application/json",
        }
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        status_code = response.status_code
        response = json.loads(response.content)
        return make_json_response(status_code, response)
