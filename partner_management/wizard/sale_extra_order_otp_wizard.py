from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleExtraOrderOtpWizard(models.TransientModel):
    _name = "sale.extra.order.otp.wizard"
    _description = "Verify Sub-customer Mobile Before Extra Order"

    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Sub-customer",
        required=True,
        readonly=True,
    )
    mobile = fields.Char(required=True)
    country_id = fields.Many2one("res.country", string="Country", required=True)
    otp_code = fields.Char(string="OTP Code")
    extra_order_type = fields.Selection(
        [
            ("intern", "Intern"),
            ("extern", "Extern"),
        ],
        string="Extra Order Type",
        required=True,
        default="intern",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env["sale.order"].browse(
            values.get("sale_order_id")
            or self.env.context.get("default_sale_order_id")
        )
        partner = order.subordinate_id
        if partner:
            values.setdefault("partner_id", partner.id)
            values.setdefault("mobile", partner.mobile)
            values.setdefault(
                "country_id",
                partner.country_id.id or order.partner_id.country_id.id,
            )
        values.setdefault(
            "extra_order_type",
            self.env.context.get("default_extra_order_type") or "intern",
        )
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

    def action_verify_and_create_extra_order(self):
        """Validate OTP, verify the Sub-customer, then create Extra Order."""
        self.ensure_one()
        order = self.sale_order_id
        partner = self.partner_id
        if not order or order.subordinate_id != partner:
            raise UserError(_(
                "This verification wizard is no longer valid for the sale order."
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
        return order.with_context(
            skip_extra_order_type_wizard=True,
            extra_order_type=self.extra_order_type or "intern",
        ).action_create_extra_sale_order()
