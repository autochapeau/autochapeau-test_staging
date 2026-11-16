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


def _infinito_response_accepted(response):
    """Provider acceptance does not prove delivery to the recipient's handset."""
    try:
        payload = response.json()
    except ValueError:
        payload = parse_qs(response.text)
    if not isinstance(payload, dict):
        return False
    status = payload.get("statustext")
    if isinstance(status, list):
        status = status[0] if status else ""
    return str(status or "").strip().lower() == "success"


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
        _logger.warning("SMS provider request failed (%s, HTTP %s)", type(error).__name__, status)
        raise UserError(_("The SMS service is unavailable. Please try again later.")) from None
    if not result:
        _logger.warning("SMS provider rejected a send request")
        raise UserError(_("The SMS provider did not accept the message. Please contact support."))
    return True
