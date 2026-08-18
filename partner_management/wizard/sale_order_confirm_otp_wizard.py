from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleOrderConfirmOtpWizard(models.TransientModel):
    _name = "sale.order.confirm.otp.wizard"
    _description = "Verify Customer Mobile Before Confirming Sale Order"

    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        readonly=True,
    )
    mobile = fields.Char(required=True)
    country_id = fields.Many2one("res.country", string="Country", required=True)
    otp_code = fields.Char(string="OTP Code")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env["sale.order"].browse(
            values.get("sale_order_id")
            or self.env.context.get("default_sale_order_id")
        )
        partner = order.partner_id
        if partner:
            values.setdefault("partner_id", partner.id)
            values.setdefault("mobile", partner.mobile)
            values.setdefault("country_id", partner.country_id.id)
        return values

    def action_send_otp(self):
        self.ensure_one()
        Partner = self.env["res.partner"]
        if not self.mobile:
            raise ValidationError(_("Please enter the mobile number first."))
        if not self.country_id:
            raise ValidationError(_("Please select the country first."))

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
                    "Enter it below, then confirm. %s"
                )
                % (phone, otp),
                "type": "success",
                "sticky": False,
            },
        }

    def action_verify_and_confirm(self):
        """Validate OTP, verify the customer, then confirm the sale order."""
        self.ensure_one()
        order = self.sale_order_id
        partner = self.partner_id
        if not order or order.partner_id != partner:
            raise UserError(_(
                "This verification wizard is no longer valid for the sale order."
            ))
        if order.order_type not in ("intern", "extern"):
            raise UserError(_(
                "OTP confirmation is only required for Intern and Extern orders."
            ))
        if not self.otp_code or not str(self.otp_code).strip():
            raise ValidationError(_(
                "Please enter the OTP code sent to the mobile number."
            ))

        Partner = self.env["res.partner"]
        Partner._assert_mobile_otp_valid(self.mobile, self.otp_code)
        partner.with_context(skip_partner_mobile_otp=True).write({
            "mobile": self.mobile,
            "country_id": self.country_id.id,
            "mobile_verified": True,
            "active": True,
        })
        order.with_context(skip_confirm_otp_wizard=True).action_confirm()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
