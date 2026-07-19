import math
import random

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CarCheckin(models.Model):
    def action_pickup_now(self):
        """Set the pickup date to the current system date/time."""
        self.ensure_one()
        self.date = fields.Datetime.now()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.model
    def _partner_ids_by_phone_term(self, term):
        normalized = "".join(ch for ch in (term or "") if ch.isdigit())
        if not normalized:
            return []
        like_term = f"%{normalized}%"
        self.env.cr.execute(
            """
                SELECT id
                  FROM res_partner
                 WHERE regexp_replace(COALESCE(phone, ''), '\\D', '', 'g') LIKE %s
                    OR regexp_replace(COALESCE(mobile, ''), '\\D', '', 'g') LIKE %s
            """,
            [like_term, like_term],
        )
        return [row[0] for row in self.env.cr.fetchall()]

    @api.depends("partner_id.phone", "partner_id.mobile")
    def _compute_partner_phone_search(self):
        for rec in self:
            phone = rec.partner_id.phone or ""
            mobile = rec.partner_id.mobile or ""
            rec.partner_phone_search = " ".join(
                [
                    "".join(ch for ch in phone if ch.isdigit()),
                    "".join(ch for ch in mobile if ch.isdigit()),
                ]
            ).strip()

    @api.model
    def _search_partner_phone_search(self, operator, value):
        if operator not in ("ilike", "like", "=", "=ilike", "=like"):
            return [("id", "=", 0)]
        partner_ids = self._partner_ids_by_phone_term(value)
        if not partner_ids:
            return [("id", "=", 0)]
        return [("partner_id", "in", partner_ids)]

    @api.model
    def _name_search(self, name="", args=None, operator="ilike", limit=100, order=None):
        args = list(args or [])
        result_ids = super()._name_search(name=name, args=args,
                                          operator=operator, limit=limit, order=order)
        if not name or (limit and len(result_ids) >= limit):
            return result_ids

        partner_ids = self._partner_ids_by_phone_term(name)
        if not partner_ids:
            return result_ids

        remaining = False if not limit else max(limit - len(result_ids), 0)
        extra_args = args + [("id", "not in", result_ids),
                             ("partner_id", "in", partner_ids)]
        extra_ids = list(self._search(
            extra_args, limit=remaining, order=order))
        return result_ids + extra_ids

    def _check_required_check_items(self):
        # Only check required items - they must be checked
        missing_required = self.car_check_item_ids.filtered(
            lambda l: l.car_check_item_id and l.car_check_item_id.required and not l.checked)
        if missing_required:
            item = missing_required[0]
            raise ValidationError(
                _("The item '%s' should be checked, it is required.") % item.car_check_item_id.name)

    _name = "car.checkin"
    _inherit = ["mail.thread", "mail.activity.mixin", "portal.mixin"]
    _description = "Car checkin"

    branch_id = fields.Many2one(
        'hr.department',
        string='Branch',
        domain="[('department_type', '=', 'branche')]",
        readonly=True,
        help="Branch selected during the appointment."
    )

    active = fields.Boolean(default=True)
    name = fields.Char(readonly=True, copy=False)

    date = fields.Datetime(readonly=True)
    company_id = fields.Many2one(
        "res.company", string="Agency", required=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one("hr.employee", "Employee")

    vehicle_id = fields.Many2one("fleet.vehicle", required=True, readonly=True)
    vehicle_license_plate = fields.Char(related="vehicle_id.license_plate")
    vehicle_vin_sn = fields.Char(related="vehicle_id.vin_sn")
    vehicle_color_id = fields.Many2one(related="vehicle_id.vehicle_color_id")
    vehicle_size = fields.Selection(related="vehicle_id.size")
    odometer = fields.Float(readonly=True)

    partner_id = fields.Many2one(
        "res.partner", "Customer", required=True, readonly=True)
    partner_phone = fields.Char(related="partner_id.phone")
    partner_phone_search = fields.Char(
        string="Phone Search",
        compute="_compute_partner_phone_search",
        search="_search_partner_phone_search",
    )
    partner_email = fields.Char(related="partner_id.email")

    sale_order_id = fields.Many2one(
        "sale.order", string="Sale Order", readonly=True)

    photo_attachment_ids = fields.Many2many("ir.attachment", string="Photos")
    notes = fields.Text()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("progress", "Waiting for customer approval"),
            ("done", "Done"),
            ("canceled", "Canceled"),
        ],
        default="draft",
        tracking=True,
    )

    signature = fields.Image(copy=False, attachment=True,
                             max_width=1024, max_height=1024, readonly=True)
    signed_by = fields.Char(copy=False, readonly=True)
    signed_on = fields.Datetime(copy=False, readonly=True)
    otp_code = fields.Char(string="temporary password")
    otp_code_input = fields.Char(string="Enter OTP")

    def _generate_otp_code(self):
        """Generate One time password"""
        # Declare a digits variable which stores all digits
        digits = "0123456789"
        OTP = ""
        # length of password can be changed by changing value in range
        for _i in range(4):
            OTP += digits[math.floor(random.random() * 10)]
        return OTP

    def _default_check_items(self):
        # Take items configured for check-in or with neither check_in nor check_out checked
        check_items = self.env["car.check.item"].search([
            '|',
            ('check_in', '=', True),
            '&', ('check_in', '=', False), ('check_out', '=', False)
        ])
        return [
            (
                0,
                0,
                {
                    "car_check_item_id": item.id,
                },
            )
            for item in check_items
        ]

    car_check_item_ids = fields.One2many(
        "car.checkin.check.item", "car_checkin_id", readonly=True, default=_default_check_items
    )

    def create(self, vals):
        """
        Add Sequence Number and always propagate branch from appointment if present.
        This checks both the sale order's appointment and a direct appointment_id in vals.
        """
        # Try to get branch from sale order's appointment
        if not vals.get('branch_id') and vals.get('sale_order_id'):
            sale_order = self.env['sale.order'].browse(vals['sale_order_id'])
            if sale_order.appointment_id and sale_order.appointment_id.branch_id:
                vals['branch_id'] = sale_order.appointment_id.branch_id.id
        # Try to get branch from direct appointment_id if present
        if not vals.get('branch_id') and vals.get('appointment_id'):
            appointment = self.env['car.appointment'].browse(
                vals['appointment_id'])
            if appointment.branch_id:
                vals['branch_id'] = appointment.branch_id.id
        checkin = super().create(vals)
        if checkin:
            checkin.name = checkin.env["ir.sequence"].next_by_code(
                "car.checkin.seq")
        return checkin

    def write(self, vals):
        if vals.get("signature"):
            vals["state"] = "done"
            self.env["fleet.vehicle.odometer"].create(
                {
                    "value": self.odometer,
                    "date": self.date or fields.Date.context_today(self),
                    "vehicle_id": self.vehicle_id.id,
                }
            )
        return super().write(vals)

    def action_progress(self):
        self.ensure_one()
        if not self.date:
            raise ValidationError(_("Please add the check-in time"))
        if not self.odometer:
            raise ValidationError(_("Please add the car odometer"))
        # Required check items verification
        self._check_required_check_items()
        self.state = "progress"
        # Send OTP SMS
        self._send_otp_sms()

    def action_cancel(self):
        self.state = "canceled"

    def action_preview_checkin(self):
        self.ensure_one()
        # Required check items verification
        self._check_required_check_items()
        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": self.get_portal_url(),
        }

    def send_sms_message(self, phone_number, message_text):
        """Send SMS using the SMS wizard."""
        wizard = (
            self.env["sms.message.wizard"]
            .with_context(active_id=self.id, active_model=self._name, lang=self.partner_id.lang)
            .create(
                {
                    "mobile": phone_number,
                    "message": message_text,
                }
            )
        )
        try:
            return wizard.send_sms()
        except Exception as e:
            raise ValidationError(
                _("Failed to send SMS: %s") % str(e)) from None

    def _send_otp_sms(self):
        """Send the OTP SMS to the customer."""
        self.ensure_one()
        phone = self.partner_id.mobile or self.partner_id.phone
        country_code = self.partner_id.country_id.phone_code if self.partner_id.country_id else ""
        if phone and not phone.startswith("+") and country_code:
            phone = f"+{country_code}{phone}"
        otp = self._generate_otp_code()
        self.otp_code = otp
        #  message with OTP
        message_text_en = (
            "Your verification code to confirm your car check-in is: %s") % otp
        message_text_ar = ("رمزالتحقق لتأكيد تسليم سيارتك هو: %s") % otp
        lang = (self.partner_id.lang or "en_US").lower()

        if lang.startswith("ar_001"):
            message_text = message_text_ar
        else:
            message_text = message_text_en
        self.send_sms_message(phone, message_text)

    def action_confirm(self):
        """
        Confirm the check-in by verifying the entered OTP.
        If the OTP is correct, move to 'done' state and send confirmation SMS.
        """
        self.ensure_one()
        if not self.otp_code_input:
            raise ValidationError(_("Please enter the OTP."))

        if self.otp_code_input.strip() != self.otp_code:
            raise ValidationError(_("Incorrect OTP code."))
        self.state = "done"
        self.otp_code_input = False

        # Prepare the message to send after confirmation
        message_text_en = (
            "Dear Customer,\n\n"
            "We have received your car [%(plate)s]\n"
            "at [%(branch)s] branch for the order [%(order)s].\n\n"
            "If you have any questions or would like to review the notes, please contact us at 059999000.\n\n"
            "Thank you for choosing us!"
        ) % {
            "plate": self.vehicle_license_plate or "",
            "branch": self.company_id.name or "",
            "order": self.name or "",
        }
        message_text_ar = (
            "عميلنا العزيز،\n\n"
            "لقد استلمنا سيارتك [%(plate)s]\n"
            "في فرع [%(branch)s] لطلبك رقم [%(order)s].\n\n"
            "إذا كانت لديك أي أسئلة أو ترغب في مراجعة الملاحظات، يرجى التواصل معنا على الرقم 059999000.\n\n"
            "شكرًا لاختيارك لنا!"
        ) % {
            "plate": self.vehicle_license_plate or "",
            "branch": self.company_id.name or "",
            "order": self.name or "",
        }

        # Retrieve the customer's phone number
        phone = self.partner_id.mobile or self.partner_id.phone
        country_code = self.partner_id.country_id.phone_code if self.partner_id.country_id else ""
        if phone and not phone.startswith("+") and country_code:
            phone = f"+{country_code}{phone}"
        if phone:
            lang = (self.partner_id.lang or "en_US").lower()

            if lang.startswith("ar_001"):
                message_text = message_text_ar
            else:
                message_text = message_text_en
            self.send_sms_message(phone, message_text)

    def get_portal_url(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None):
        """
        Get a portal url for this model, including access_token.
        The associated route must handle the flags for them to have any effect.
        - suffix: string to append to the url, before the query string
        - report_type: report_type query string, often one of: html, pdf, text
        - download: set the download query string to true
        - query_string: additional query string
        - anchor: string to append after the anchor #
        """
        self.ensure_one()
        # flake8: noqa: UP031
        url = self.access_url + "%s?access_token=%s%s%s%s%s" % (
            suffix if suffix else "",
            self._portal_ensure_token(),
            "&report_type=%s" % report_type if report_type else "",
            "&download=true" if download else "",
            query_string if query_string else "",
            "#%s" % anchor if anchor else "",
        )
        return url

    def _compute_access_url(self):
        res = super()._compute_access_url()
        for checkin in self:
            checkin.access_url = f"/my/checkin/{checkin.id}"
        return res

    def _has_to_be_signed(self):
        self.ensure_one()
        return self.state == "progress" and not self.signature

    def action_checkin_send(self):
        """Opens a wizard to compose an email, with relevant mail template loaded by default"""
        self.ensure_one()
        mail_template = self.env.ref(
            "cars_management.email_template_car_checkin")
        ctx = {
            "default_model": "car.checkin",
            "default_res_ids": self.ids,
            "default_template_id": mail_template.id if mail_template else None,
            "default_composition_mode": "comment",
            "default_email_layout_xmlid": "mail.mail_notification_layout_with_responsible_signature",
            "force_email": True,
        }
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mail.compose.message",
            "views": [(False, "form")],
            "view_id": False,
            "target": "new",
            "context": ctx,
        }


class CarCheckinCheckItem(models.Model):
    _name = "car.checkin.check.item"
    _description = "Car checkin check Item"

    car_check_item_id = fields.Many2one("car.check.item")
    checked = fields.Boolean(default=False)
    car_checkin_id = fields.Many2one("car.checkin")
