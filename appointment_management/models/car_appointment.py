
from datetime import timedelta
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CarAppointment(models.Model):
    _name = "car.appointment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Car Appointment"
    _order = "id desc"

    @api.onchange('partner_id')
    def _onchange_partner_id_set_sale_order(self):
        if self.partner_id:
            sale_order = self.env['sale.order'].search([
                ('partner_id', '=', self.partner_id.id)
            ], order='id desc', limit=1)
            if sale_order:
                self.sale_order_id = sale_order.id

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

    active = fields.Boolean(default=True)
    name = fields.Char(string="Ref.", readonly=True, copy=False)
    appointment_slot_id = fields.Many2one(
        "car.appointment.slot", required=True)
    start_date = fields.Datetime(related="appointment_slot_id.start_date")
    finish_date = fields.Datetime(related="appointment_slot_id.finish_date")
    company_id = fields.Many2one(
        "res.company", string="Agency", default=lambda self: self.env.company, required=True)

    vehicle_id = fields.Many2one("fleet.vehicle", required=True, readonly=True)
    vehicle_license_plate = fields.Char(related="vehicle_id.license_plate")
    vehicle_vin_sn = fields.Char(related="vehicle_id.vin_sn")
    vehicle_color_id = fields.Many2one(related="vehicle_id.vehicle_color_id")
    vehicle_size = fields.Selection(related="vehicle_id.size")

    partner_id = fields.Many2one(
        "res.partner", "Customer", required=True, readonly=True)
    partner_phone = fields.Char(related="partner_id.phone")
    partner_phone_search = fields.Char(
        string="Phone Search",
        compute="_compute_partner_phone_search",
        search="_search_partner_phone_search",
    )
    partner_email = fields.Char(related="partner_id.email")

    branch_id = fields.Many2one(
        "hr.department",
        string="Branche",
        domain="[('department_type', '=', 'branche')]",
        help="Branch linked to this appointment."
    )

    service_ids = fields.One2many(
        "car.appointment.service", "appointment_id", string="Services")
    product_ids = fields.One2many(
        "car.appointment.product", "appointment_id", string="Products")
    sale_order_id = fields.Many2one("sale.order")
    maintenance_slot_id = fields.Many2one(
        "car.appointment.slot", string="Scheduled maintenance appointment")
    car_transportation_service = fields.Boolean()
    car_transportation_date = fields.Datetime()

    confirmation_date = fields.Datetime(readonly=True, copy=False)
    state = fields.Selection(
        [
            ("waiting", "Waiting"),
            ("confirmed", "Confirmed"),
            ("canceled", "Canceled"),
        ],
        default="waiting",
        tracking=True,
    )

    car_checkin_id = fields.Many2one("car.checkin", readonly=True)

    def create(self, vals):
        """Add sequence and sync branch/analytic account to the linked sale order."""
        # Auto-link sale_order when needed
        if vals.get("partner_id") and not vals.get("sale_order_id"):
            sale_order = self.env["sale.order"].search([
                ("partner_id", "=", vals.get("partner_id"))
            ], order="id desc", limit=1)
            if sale_order:
                vals["sale_order_id"] = sale_order.id

        appointment = super().create(vals)
        if appointment:
            appointment.name = appointment.env["ir.sequence"].next_by_code(
                "car.appointment.seq")
            # Sync branch/analytic account to linked sale.order
            if appointment.sale_order_id and appointment.branch_id:
                update_vals = {"branch_id": appointment.branch_id.id}
                if appointment.branch_id.analytic_account_id:
                    update_vals["analytic_account_id"] = appointment.branch_id.analytic_account_id.id
                appointment.sale_order_id.write(update_vals)
        return appointment

    def write(self, vals):
        res = super().write(vals)
        # Sync branch/analytic account to linked sale.order when changed
        for appointment in self:
            if appointment.sale_order_id and appointment.branch_id:
                update_vals = {"branch_id": appointment.branch_id.id}
                if appointment.branch_id.analytic_account_id:
                    update_vals["analytic_account_id"] = appointment.branch_id.analytic_account_id.id
                appointment.sale_order_id.write(update_vals)
        return res

    def action_done(self):
        # Verify the responsibility of the slot
        self.ensure_one()
        if not self.appointment_slot_id.is_available:
            UserError(_("Slot %s is not available") %
                      str(self.appointment_slot_id.start_date))
        message = _("Your appointment has been confirmed")
        self.notify_customer(message)
        self_vals = {
            "state": "confirmed",
            "confirmation_date": fields.Datetime.now(),
        }
        # Create a car check-in
        if not self.car_checkin_id:
            checkin_vals = {
                "appointment_id": self.id,
                "partner_id": self.partner_id.id,
                "vehicle_id": self.vehicle_id.id,
                "company_id": self.company_id.id,
            }
            if self.sale_order_id:
                checkin_vals["sale_order_id"] = self.sale_order_id.id
            car_checkin = self.env["car.checkin"].sudo().create(checkin_vals)
            self_vals["car_checkin_id"] = car_checkin.id
        self.write(self_vals)
        if self.sale_order_id and self.sale_order_id.state == "sale":
            # SMS sending disabled to avoid blocking error if message model is missing
            if self.partner_id.email:
                mail_template = self.env.ref(
                    "appointment_management.email_template_appointment_confirmation", raise_if_not_found=False
                )
                if mail_template:
                    mail_template.send_mail(self.id, force_send=True)

    def _send_appointment_sms(self):
        """Send confirmation SMS using message.model if available."""
        self.ensure_one()
        model = self.env["ir.model"]._get(self._name)
        message_model = self.env["message.model"].search(
            [("model_ids", "in", [model.id])], limit=1)
        phone = self.partner_id.mobile or self.partner_id.phone
        # Add country code prefix if available and phone doesn't already include it
        country_code = self.partner_id.country_id.phone_code if self.partner_id.country_id else ""
        if phone and not phone.startswith("+") and country_code:
            phone = f"+{country_code}{phone}"
        self.send_sms_message(phone, message_model)

    def send_sms_message(self, phone_number, message_model):
        """Call the SMS wizard to send a formatted message."""
        self.ensure_one()
        wizard = (
            self.env["sms.message.wizard"]
            .with_context(active_id=self.id, active_model=self._name, lang=self.partner_id.lang)
            .create(
                {
                    "mobile": phone_number,
                    "message_model_id": message_model.id,
                    "message": message_model.message,
                }
            )
        )
        wizard._onchange_message_model_id()
        try:
            return wizard.send_sms()
        except Exception as e:
            raise ValidationError(
                _("Failed to send SMS : %s") % str(e)) from None

    def action_cancel(self):
        self.ensure_one()
        self.state = "canceled"

    def action_edit_appointment(self):
        """Edit appointment after confirmation."""
        self.ensure_one()
        if self.confirmation_date + timedelta(hours=48) < fields.Datetime.now():
            raise UserError(
                _("Appointment edition is allowed only within 48 hours"))
        self.state = "waiting"

    def action_cancel_appointment(self):
        """Cancel appointment after confirmation."""
        self.ensure_one()
        if self.confirmation_date + timedelta(hours=72) < fields.Datetime.now():
            raise UserError(
                _("Appointment cancellation is allowed only within 72 hours"))
        self.state = "canceled"

    def notify_customer(self, message):
        # Send an email
        self.ensure_one()
        mail_template = self.env.ref(
            "appointment_management.email_template_appointment_notify")
        mail_template.with_context(email_message=message).send_mail(
            self.id, force_send=False)

    @api.model
    def _notify_customers_upcoming_appointments(self):
        # Get appointments within 1 day
        appointments = self.search(
            [
                ("state", "=", "confirmed"),
                ("start_date", "<", fields.Datetime.now()),
                ("start_date", ">=", fields.Datetime.now() - timedelta(days=1)),
            ]
        )
        for appointment in appointments:
            message = _(
                "Dear Customer, this is a reminder about your upcoming appointment. "
                "Ref %s. We look forward to serving you."
            ) % appointment.name
            appointment.notify_customer(message)

    @api.model
    def retrieve_dashboard(self):
        """This function returns the values to populate the custom dashboard in
        the appointment views.
        """
        self.check_access_rights("read")
        result = {}
        app = self.env["car.appointment"]
        result["all_waiting"] = app.search_count(
            [("state", "=", "waiting"), ("start_date", ">=", fields.Datetime.now())]
        )
        result["all_confirmed"] = app.search_count(
            [("state", "=", "confirmed")])
        result["all_cancelled"] = app.search_count(
            [("state", "=", "cancelled")])
        return result


class CarAppointmentService(models.Model):
    _name = "car.appointment.service"
    _description = "Car Appointment Service"
    _rec_name = "product_id"

    product_id = fields.Many2one(
        "product.product", string="Service", domain="[('type', '=', 'service')]")
    appointment_id = fields.Many2one("car.appointment", string="Appointment")


class CarAppointmentProduct(models.Model):
    _name = "car.appointment.product"
    _description = "Car Appointment Product"
    _rec_name = "product_id"

    product_id = fields.Many2one(
        "product.product", string="Product", required=True, domain="[('detailed_type', '!=', 'service')]"
    )
    quantity = fields.Float()
    appointment_id = fields.Many2one("car.appointment", string="Appointment")
