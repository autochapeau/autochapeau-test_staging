from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    login_sms_date = fields.Datetime()
    last_otp = fields.Char()
    otp_attempts = fields.Integer(string="OTP Attempts", default=0)

    @api.model
    def signup(self, values, token=None):
        if token:
            return super().signup(values, token=token)
        else:
            if values.get("email"):
                values["email"] = values.get("email")
            else:
                values.pop("email", None)

            self._signup_create_user(values)
            return (values.get("login"), values.get("password"))
