import logging
import re
from urllib.parse import parse_qs

import requests

from odoo import _
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


def normalize_phone(phone, country_code="966"):
    value = re.sub(r"[\s()\-]", "", str(phone or ""))
    prefix = str(country_code).lstrip("+")
    if value.startswith("00"):
        value = "+" + value[2:]
    elif value.startswith("0"):
        value = "+" + prefix + value[1:]
    elif not value.startswith("+"):
        value = "+" + (value if value.startswith(prefix) else prefix + value)
    if value.startswith("+" + prefix + "0"):
        value = "+" + prefix + value[len(prefix) + 2:]
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
        raise UserError(_("Enter a valid mobile number including its country code."))
    return value


def _infinito_payload(response):
    try:
        payload = response.json()
    except ValueError:
        payload = parse_qs(response.text)
    return payload if isinstance(payload, dict) else {}


def _scalar(value):
    return value[0] if isinstance(value, list) and value else value


def _infinito_response_accepted(response):
    """Accept both documented response formats, never per-recipient errors."""
    if response.status_code != 200:
        return False
    payload = _infinito_payload(response)
    status = str(_scalar(payload.get("statustext")) or "").strip().lower()
    code = str(_scalar(payload.get("statuscode")) or "0")
    acknowledgements = payload.get("messageack") or {}
    if not isinstance(acknowledgements, dict):
        return False
    guids = acknowledgements.get("guids") or []
    if not isinstance(guids, list) or any(not isinstance(row, dict) or row.get("errors") for row in guids):
        return False
    if status == "success" and code in ("0", "200"):
        return True
    return bool(str(payload.get("status") or "").lower() == "success"
                and code == "200" and status == "ok" and guids
                and all(row.get("guid") for row in guids))


def _infinito_failure_category(response):
    """Only return fixed diagnostic labels; response bodies may contain secrets."""
    if response is None:
        return "network"
    if response.status_code == 403 or response.text.strip().lower() == "forbidden":
        return "api_access_denied"
    if response.status_code == 401:
        return "authentication_rejected"
    if response.status_code == 429:
        return "rate_limited"
    code = str(_scalar(_infinito_payload(response).get("statuscode")) or "")
    return {"52992": "authentication_rejected", "52996": "token_rejected",
            "57089": "contract_expired", "57090": "credit_expired",
            "57091": "account_disabled", "57092": "account_expired",
            "57093": "token_disabled", "28680": "sender_rejected",
            "28682": "recipient_rejected"}.get(code, "provider_rejected")


def send_sms(phone, message=None):
    """Send SMS to the given phone number using a custom SMS API."""
    infinito_client_id = request.env["ir.config_parameter"].sudo().get_param("infinito_client_id", "")
    infinito_client_password = request.env["ir.config_parameter"].sudo().get_param("infinito_client_password", "")
    if not infinito_client_id or not infinito_client_password:
        raise UserError(_("The SMS provider is not configured. Please contact support."))
    phone = normalize_phone(phone)
    if not message:
        raise UserError(_("The SMS message is empty."))

    # Evaluate the message template
    formatted_message = message
    payload = {
        "clientid": infinito_client_id,
        "clientpassword": infinito_client_password,
        "from": "AutoChapeau",
        # ValueFirst expects country-code-prefixed digits without punctuation.
        "to": phone.lstrip("+"),
        "text": formatted_message,
    }
    result = False
    try:
        response = requests.get("https://api.goinfinito.me/unified/v2/send", params=payload, timeout=15, allow_redirects=False)
        response.raise_for_status()

        result = response.status_code == 200 and _infinito_response_accepted(response)
    except requests.RequestException as error:
        # URLs contain credentials and OTP text, so never log the request URL.
        status = getattr(getattr(error, "response", None), "status_code", None)
        _logger.warning("SMS provider request failed (%s, HTTP %s, reason=%s)",
                        type(error).__name__, status,
                        _infinito_failure_category(getattr(error, "response", None)))
        raise UserError(_("The SMS service is unavailable. Please try again later.")) from None
    if not result:
        _logger.warning("SMS provider rejected a send request (reason=%s)",
                        _infinito_failure_category(response))
        raise UserError(_("The SMS provider did not accept the message. Please contact support."))
    return True
