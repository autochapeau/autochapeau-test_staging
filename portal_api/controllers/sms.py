import logging
from urllib.parse import parse_qs

import requests

from odoo import _
from odoo.http import request

_logger = logging.getLogger(__name__)


def send_sms(phone, message=None):
    """Send SMS to the given phone number using a custom SMS API."""
    infinito_client_id = request.env["ir.config_parameter"].sudo().get_param("infinito_client_id", "")
    infinito_client_password = request.env["ir.config_parameter"].sudo().get_param("infinito_client_password", "")

    # Evaluate the message template
    formatted_message = message
    payload = {
        "clientid": infinito_client_id,
        "clientpassword": infinito_client_password,
        "from": "AutoChapeau",
        "to": phone,
        "text": formatted_message,
    }
    result = False
    try:
        response = requests.get("https://api.goinfinito.me/unified/v2/send", params=payload, timeout=10)
        parsed_params = parse_qs(response.text)

        if parsed_params.get("statustext") == "Success":
            context = request.env.context or {}
            model_obj = request.env[context.get("active_model")]
            rec = model_obj.browse(context.get("active_id"))
            rec.message_post(
                body=request.message,
                subject=_("SMS Sent"),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        else:
            action_message = response.text
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": action_message,
                    "type": "warning",
                    "sticky": True,
                },
            }
    except Exception as e:
        _logger.info("Infinito server request Failed: %s", e)
    return result
