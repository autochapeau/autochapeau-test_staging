from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    title = fields.Char()
    owner_type = fields.Selection(
        [("individual", "Individual"), ("company", "Company")], string="Owner Type", default="individual")
    car_owner_name = fields.Char(string="Name", translate=True)
    car_owner_mobile = fields.Char(string="Mobile")
    car_owner_email = fields.Char(string="Email")
    car_owner_address = fields.Char(string="Address", translate=True)
    partner_id = fields.Many2one("res.partner", "Owner")
    partner_phone = fields.Char(related="partner_id.phone")
    partner_mobile = fields.Char(related="partner_id.mobile")
    partner_phone_search = fields.Char(
        string="Phone Search",
        compute="_compute_partner_phone_search",
        search="_search_partner_phone_search",
    )
    vehicle_color_id = fields.Many2one("vehicle.color")

    size = fields.Selection(related="model_id.size")
    company_id = fields.Many2one("res.company", string="Agency")
    available_services_count = fields.Integer(
        compute="_compute_available_services_count")
    checkin_count = fields.Integer(compute="_compute_checkin_count")
    checkout_count = fields.Integer(compute="_compute_checkout_count")

    plate_letters_ar = fields.Char(
        string="Arabic Letters", help="The three-letter part in Arabic.")
    plate_letters = fields.Char(
        string="Latin Letters", help="The three-letter part in Latin.")
    plate_numbers_ar = fields.Char(
        string="Arabic Numbers", help="The numeric part in Arabic numerals (Hindi).")
    plate_numbers = fields.Char(
        string="Western Arabic Numbers", help="The numeric part in Western Arabic numerals.")

    license_plate = fields.Char(
        compute="_compute_license_plate", store=True, tracking=True)

    unverified_model_name = fields.Char(
        copy=False, readonly=True, help="Useful when the portal customer car brand doesn't exist in the system."
    )
    display_name = fields.Char(compute="_compute_display_name")

    @api.model
    def create(self, vals):
        if vals.get("unverified_model_name"):
            car_model_vals = {
                "name": vals.get("unverified_model_name"),
                "brand_id": self.env.ref("cars_management.unknown_manufacturer").id,
            }
            car_model = self.env["fleet.vehicle.model"].create(car_model_vals)
            vals["model_id"] = car_model.id
            # Create car and notify cars managers about the new model to verify.
            car = super().create(vals)
            users = self.env.ref("fleet.fleet_group_manager").users
            for user in users:
                car.activity_schedule(
                    "cars_management.mail_act_car_model_verification",
                    user_id=user.id,
                )
            return car
        return super().create(vals)

    def name_get(self):
        """Return formatted vehicle names."""
        return [(vehicle.id, vehicle.display_name or "") for vehicle in self]

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
            # Keep only digits to make matching robust against spaces/symbols.
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
    def _name_search(self, name="", domain=None, operator="ilike", limit=100, order=None):
        domain = list(domain or [])
        result_ids = super()._name_search(name=name, domain=domain,
                                          operator=operator, limit=limit, order=order)
        if not name or (limit and len(result_ids) >= limit):
            return result_ids

        partner_ids = self._partner_ids_by_phone_term(name)
        if not partner_ids:
            return result_ids

        remaining = False if not limit else max(limit - len(result_ids), 0)
        extra_domain = domain + \
            [("id", "not in", result_ids), ("partner_id", "in", partner_ids)]
        extra_ids = list(self._search(
            extra_domain, limit=remaining, order=order))
        return result_ids + extra_ids

    @api.constrains("vin_sn")
    def _check_vin_sn(self):
        for vehicle in self:
            if vehicle.vin_sn and len(vehicle.vin_sn) != 17:
                raise ValidationError(
                    _("The Chassis Number should be 17 characters."))

    @api.depends("plate_letters_ar", "plate_letters", "plate_numbers_ar", "plate_numbers")
    def _compute_license_plate(self):
        for vehicle in self:
            parts = [
                vehicle.plate_letters_ar or "",
                vehicle.plate_numbers_ar or "",
                vehicle.plate_numbers or "",
                vehicle.plate_letters or "",
            ]
            vehicle.license_plate = "-".join(filter(None, parts))

    def _compute_available_services_count(self):
        for vehicle in self:
            vehicle.available_services_count = self.env["product.product"].search_count(
                vehicle._get_available_service_domain()
            )

    def _compute_checkin_count(self):
        for vehicle in self:
            vehicle.checkin_count = self.env["car.checkin"].search_count(
                [("vehicle_id", "=", vehicle.id)])

    def _compute_checkout_count(self):
        for vehicle in self:
            vehicle.checkout_count = self.env["car.checkout"].search_count(
                [("vehicle_id", "=", vehicle.id)])

    @api.depends_context("lang")
    def _compute_display_name(self):
        """Compute vehicle display name based on user language and plate details."""
        for vehicle in self:
            lang = vehicle.env.context.get("lang", "en_US")
            plate_letters = vehicle.plate_letters_ar if lang.startswith(
                "ar") else vehicle.plate_letters
            plate_numbers = vehicle.plate_numbers_ar if lang.startswith(
                "ar") else vehicle.plate_numbers
            plate = (plate_numbers or "") + "-" + (plate_letters or "")
            vehicle.display_name = (
                f"{vehicle.brand_id.name or ''} / {vehicle.model_id.name or ''} / {plate.strip() or _('No Plate')}"
            )

    def action_view_available_services(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "product.product_normal_action_sell")
        action["domain"] = self._get_available_service_domain()
        action["context"] = {"default_detailed_type": "service"}
        action["view_mode"] = "kanban,form"
        kanban_view_id = self.env.ref("product.product_kanban_view").id
        form_view_id = self.env.ref("product.product_normal_form_view").id
        action["views"] = [
            [kanban_view_id, "kanban"],
            [form_view_id, "form"],
        ]
        return action

    def _get_available_service_domain(self):
        self.ensure_one()
        return [
            ("detailed_type", "=", "service"),
            ("product_template_variant_value_ids.product_attribute_value_id.code", "=", self.size),
        ]

    def action_view_checkins(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "cars_management.car_checkin_action")
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {"default_vehicle_id": self.id}
        return action

    def action_view_checkouts(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "cars_management.car_checkout_action")
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {"default_vehicle_id": self.id}
        return action

    def action_open_sms_wizard(self):
        """Open wizard to send message via SMS"""
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "infinito_sms.sms_send_message_wizard_action")
        action["context"] = {"default_mobile": self.partner_id.phone}
        return action
