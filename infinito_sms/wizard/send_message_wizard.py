import logging
import re
from urllib.parse import parse_qs

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class SmsSendMessage(models.TransientModel):
    _name = "sms.message.wizard"
    _description = "SMS Wizard"

    # ------------------------------
    # Fields
    # ------------------------------
    message = fields.Text(required=True)
    mobile = fields.Char(required=True)

    def _default_message_model_domain(self):
        context = self.env.context or {}
        model_id = self.env["ir.model"]._get(context.get("active_model")).id
        return ["|", ("model_ids", "=", model_id), ("model_ids", "=", False)]

    message_model_id = fields.Many2one("message.model", domain=_default_message_model_domain)

    # ---------------------------------
    # Methods
    # ---------------------------------

    @api.onchange("message_model_id")
    def _onchange_message_model_id(self):
        if self.message_model_id:
            context = self.env.context or {}
            model_obj = self.env[context.get("active_model")]
            rec = model_obj.browse(context.get("active_id"))
            lang = context.get("lang")
            message = self.message_model_id.with_context(lang=lang).message
            pattern = re.compile(r"{(.*?)}")
            formatted_message = pattern.sub(lambda expr: self.evaluate_expression(expr.group(1), rec), message)
            self.message = formatted_message

    def evaluate_expression(self, expression, record):
        try:
            return str(safe_eval(expression, {"o": record}))
        except Exception as e:
            raise ValidationError(
                _("Error evaluating expression '%(expression)s': %(exception)s") % (expression, str(e))
            ) from None

    def send_sms(self):
        """Send SMS"""
        infinito_client_id = self.env["ir.config_parameter"].sudo().get_param("infinito_client_id", "")
        infinito_client_password = self.env["ir.config_parameter"].sudo().get_param("infinito_client_password", "")
        params = {
            "clientid": infinito_client_id,
            "clientpassword": infinito_client_password,
            "from": "AutoChapeau",
            "to": self.mobile,
            "text": self.message,
        }
        try:
            response = requests.get("https://api.goinfinito.me/unified/v2/send", params=params, timeout=10)
            parsed_params = parse_qs(response.text)

            if parsed_params.get("statustext") == "Success":
                context = self.env.context or {}
                model_obj = self.env[context.get("active_model")]
                rec = model_obj.browse(context.get("active_id"))
                rec.message_post(
                    body=self.message,
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
