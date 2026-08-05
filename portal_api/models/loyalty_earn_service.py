# -*- coding: utf-8 -*-
"""External loyalty earn helpers (Alrajhi / Qitaf) for paid-invoice grants."""
import base64
import json
import logging
import uuid
from base64 import b64encode
from datetime import datetime, timezone

import pytz
import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from odoo import models
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)


class LoyaltyEarnService(models.AbstractModel):
    _name = "loyalty.earn.service"
    _description = "External Loyalty Earn Service"

    def earn_alrajhi(self, phone, amount, branch_code=None):
        """Credit Alrajhi Mokafaa via earn-by-sar. Returns dict with success bool."""
        ICP = self.env["ir.config_parameter"].sudo()
        base_url = ICP.get_param("alrajhi_loyalty_url")
        partner_code = ICP.get_param("alrajhi_reward.partnerCode")
        location_code = (
            branch_code
            or ICP.get_param("alrajhi_reward.locationCode")
            or ICP.get_param("alrajhi_reward.locationCodeDMM")
            or ICP.get_param("alrajhi_reward.locationCodeKHO")
        )
        if not base_url or not partner_code or not phone:
            return {"success": False, "message": "Missing Alrajhi configuration or phone"}

        transaction_number = str(uuid.uuid4())
        current_date = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        payload = {
            "partnerCode": partner_code,
            "locationCode": location_code,
            "saleTrnNo": transaction_number,
            "date": current_date,
            "mobile": phone,
            "amount": amount,
        }
        try:
            payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            private_key_path = file_path("portal_api/static/src/alrajhi/privateKey.pem")
            with open(private_key_path, "rb") as key_file:
                private_key = load_pem_private_key(key_file.read(), password=None)
            signed_hash = private_key.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())
            signature_base64 = base64.b64encode(signed_hash).decode("utf-8")

            oauth_token = self._generate_alrajhi_reward_token()
            if not oauth_token:
                return {"success": False, "message": "Failed to get Alrajhi OAuth token"}

            url = f"{base_url}/api-factory/prod/loyalty-accruals/1.0.0/earn-by-sar"
            headers = {
                "Authorization": "Bearer " + oauth_token,
                "x-signature": signature_base64,
                "Content-Type": "application/json",
            }
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            data = response.json() if response.content else {}
            # Controllers historically treated nested result.code == 200 as success.
            result = data.get("result") if isinstance(data, dict) else {}
            code = result.get("code") if isinstance(result, dict) else None
            if code == 200 or response.ok:
                return {"success": True, "response": data}
            header = result.get("header") if isinstance(result, dict) else {}
            status_code = header.get("statusCode") if isinstance(header, dict) else None
            require_alt = status_code in ("E00173", "E00145")
            return {
                "success": False,
                "require_alternate_phone": require_alt,
                "message": (header or {}).get("statusDescription")
                or result.get("message")
                or "AlRajhi loyalty error",
                "response": data,
            }
        except Exception as exc:
            _logger.exception("Alrajhi earn failed")
            return {"success": False, "message": str(exc)}

    def _generate_alrajhi_reward_token(self):
        ICP = self.env["ir.config_parameter"].sudo()
        base_url = ICP.get_param("alrajhi_loyalty_url")
        client_id = ICP.get_param("alrajhi.client_id")
        client_secret = ICP.get_param("alrajhi.client_secret")
        token_vals = {
            "grant_type": "client_credentials",
            "scope": (
                "earn-by-sar earn-by-points earn-by-sar-and-ratio "
                "refund-earn-by-sar get-earn-trans-details get-earn-recon"
            ),
            "client_id": client_id,
            "client_secret": client_secret,
        }
        token_url = f"{base_url}/api-factory/prod/loyalty-accruals/oauth2/token"
        token_response = requests.post(
            token_url,
            data=token_vals,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        if not token_response.ok:
            return False
        return token_response.json().get("access_token")

    def earn_qitaf(self, phone, amount):
        """Credit Qitaf earn API. Returns dict with success bool."""
        if not phone:
            return {"success": False, "message": "Missing phone for Qitaf earn"}
        ICP = self.env["ir.config_parameter"].sudo()
        endpoint = "/api/v1/earn/reward"
        qitaf_branch_id = ICP.get_param("qitaf_branch_id")
        qitaf_terminal_id = ICP.get_param("qitaf_terminal_id")
        mobile = self._parse_qitaf_phone(phone)
        ksa = pytz.timezone("Asia/Riyadh")
        payload = {
            "Amount": amount,
            "RequestDate": datetime.now(ksa).strftime("%Y-%m-%dT%H:%M:%S"),
            "Msisdn": mobile,
            "BranchId": qitaf_branch_id,
            "TerminalId": qitaf_terminal_id,
        }
        try:
            response = self._qitaf_http_post(endpoint, json_body=payload)
            if response.get("success"):
                return {"success": True, "response": response.get("data")}
            error = response.get("error") or {}
            if isinstance(error, list) and error:
                error = error[0]
            code = error.get("code") if isinstance(error, dict) else None
            return {
                "success": False,
                "require_alternate_phone": code == 9999,
                "message": (error.get("description") if isinstance(error, dict) else None)
                or "Qitaf earn error",
                "response": response,
            }
        except Exception as exc:
            _logger.exception("Qitaf earn failed")
            return {"success": False, "message": str(exc)}

    def _parse_qitaf_phone(self, number):
        number = number or ""
        if number.startswith("966") and len(number) == 12:
            return "0" + number[3:]
        return number

    def _qitaf_http_post(self, endpoint, json_body=None):
        ICP = self.env["ir.config_parameter"].sudo()
        base_url = ICP.get_param("qitaf_loyalty_url")
        client_cert = file_path("portal_api/static/src/certs/qitaf_client_cert.pem")
        client_key = file_path("portal_api/static/src/certs/qitaf_client_key.key")
        ca_cert = file_path("portal_api/static/src/certs/qitaf-ca-chain.crt")
        headers = self._qitaf_default_headers()
        response = requests.post(
            f"{base_url}{endpoint}",
            cert=(client_cert, client_key),
            verify=ca_cert,
            headers=headers,
            json=json_body,
            timeout=15,
        )
        try:
            data = response.json()
        except ValueError:
            data = {"error": "Invalid JSON response", "status_code": response.status_code}
        if response.ok:
            return {"success": True, "data": data}
        return {
            "success": False,
            "status_code": response.status_code,
            "error": data.get("errors", data) if isinstance(data, dict) else str(data),
        }

    def _qitaf_default_headers(self):
        ICP = self.env["ir.config_parameter"].sudo()
        qitaf_loyalty_token = ICP.get_param("qitaf_loyalty_token")
        qitaf_username = ICP.get_param("qitaf_username")
        qitaf_password = ICP.get_param("qitaf_password")
        auth_token = b64encode(f"{qitaf_username}:{qitaf_password}".encode()).decode("ascii")
        return {
            "Accept-Language": "en-US",
            "GlobalId": str(uuid.uuid4()),
            "X-Secret-Token": qitaf_loyalty_token,
            "Authorization": f"Basic {auth_token}",
        }
