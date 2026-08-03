from odoo import _, fields, models
from odoo.exceptions import ValidationError


class PartnerSendOtpWizard(models.TransientModel):
    _name = "partner.send.otp.wizard"
    _description = "Send Mobile OTP for Customer"

    mobile = fields.Char(required=True)
    country_id = fields.Many2one("res.country", string="Country")
    partner_id = fields.Many2one("res.partner")

    def action_send_otp(self):
        self.ensure_one()
        Partner = self.env["res.partner"]
        if not self.mobile:
            raise ValidationError(_("Please enter the mobile number first."))
        # Block sending OTP to a mobile that already belongs to another partner
        # norm = Partner._normalize_mobile(self.mobile)
        # domain = [("mobile_normalized", "=", norm)]
        # if self.partner_id:
        #     domain.append(("id", "!=", self.partner_id.id))
        # duplicate = Partner.search(domain, limit=1)
        # if duplicate:
        #     raise ValidationError(_(
        #         "The mobile number '%(mobile)s' is already used by '%(name)s'."
        #     ) % {"mobile": self.mobile, "name": duplicate.display_name})

        otp = Partner._generate_otp_code()
        Partner._store_mobile_otp(self.mobile, otp)
        phone = Partner._format_phone_for_sms(self.mobile, self.country_id)
        message = _("Your verification code is: %s") % otp
        Partner._send_otp_sms_message(phone, message, partner=self.partner_id)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("OTP Sent"),
                "message": _(
                    "A verification code has been sent to %s. "
                    "Enter it in the OTP Code field, then save."
                ) % phone,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
