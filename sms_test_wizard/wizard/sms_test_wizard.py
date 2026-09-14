import logging
from urllib.parse import parse_qs

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

INFINITO_SEND_URL = "https://api.goinfinito.me/unified/v2/send"


class SmsTestWizard(models.TransientModel):
    _name = "sms.test.wizard"
    _description = "SMS Test Wizard"

    mobile = fields.Char(
        required=True,
        help="International format, e.g. +96279xxxxxxx",
    )
    message = fields.Text(required=True, default="Test SMS from AutoChapeau")
    sender = fields.Char(required=True, default="AutoChapeau")
    last_response = fields.Text(readonly=True)
    result_status = fields.Selection(
        [
            ("success", "Accepted"),
            ("failed", "Failed"),
        ],
        readonly=True,
    )

    def action_send_sms(self):
        self.ensure_one()
        icp = self.env["ir.config_parameter"].sudo()
        params = {
            "clientid": icp.get_param("infinito_client_id", ""),
            "clientpassword": icp.get_param("infinito_client_password", ""),
            "from": (self.sender or "").strip() or "AutoChapeau",
            "to": (self.mobile or "").strip(),
            "text": self.message,
        }
        if not params["clientid"] or not params["clientpassword"]:
            raise UserError(_("Infinito credentials are missing (infinito_client_id / infinito_client_password)."))
        if not params["to"]:
            raise UserError(_("Please enter a mobile number."))

        try:
            response = requests.get(INFINITO_SEND_URL, params=params, timeout=10)
            parsed = parse_qs(response.text)
            status = (parsed.get("statustext") or [""])[0]
            accepted = status == "Success"
            self.write(
                {
                    "last_response": response.text,
                    "result_status": "success" if accepted else "failed",
                }
            )
        except requests.RequestException as exc:
            _logger.exception("SMS test request failed")
            self.write(
                {
                    "last_response": str(exc),
                    "result_status": "failed",
                }
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("Test SMS"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
