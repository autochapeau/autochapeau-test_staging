from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
import re

# Same mapping as eshop-website plateConversions.ts
AR_TO_EN_DIGITS = {
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
}
EN_TO_AR_DIGITS = {v: k for k, v in AR_TO_EN_DIGITS.items()}

AR_TO_EN_LETTERS = {
    "أ": "A",
    "ب": "B",
    "ح": "J",
    "د": "D",
    "ر": "R",
    "س": "S",
    "ص": "X",
    "ط": "T",
    "ق": "G",
    "ك": "K",
    "ل": "L",
    "م": "Z",
    "ن": "N",
    "ه": "H",
    "هـ": "H",
    "و": "U",
    "ى": "V",
    "ع": "E",
}
EN_TO_AR_LETTERS = {v: k for k, v in AR_TO_EN_LETTERS.items() if k != "هـ"}
PLATE_LETTER_SELECTION = [(letter, letter) for letter in sorted(EN_TO_AR_LETTERS)]


def _convert_ar_digits_to_en(value):
    if not value:
        return value
    return "".join(AR_TO_EN_DIGITS.get(ch, ch) for ch in value)


def _convert_en_digits_to_ar(value):
    if not value:
        return value
    return "".join(EN_TO_AR_DIGITS.get(ch, ch) for ch in value)


def _convert_ar_letters_to_en(value):
    if not value:
        return value
    if value.strip() == "هـ":
        return "H"
    return "".join(AR_TO_EN_LETTERS.get(ch, ch) for ch in value)


def _convert_en_letters_to_ar(value):
    if not value:
        return value
    return "".join(EN_TO_AR_LETTERS.get(ch.upper() if ch.isalpha() else ch, ch) for ch in value)


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
    owner_country_code = fields.Char(
        related="partner_id.country_id.code",
        string="Owner Country Code",
    )
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
    plate_letter_1 = fields.Selection(
        selection=PLATE_LETTER_SELECTION,
        string="Letter 1",
    )
    plate_letter_2 = fields.Selection(
        selection=PLATE_LETTER_SELECTION,
        string="Letter 2",
    )
    plate_letter_3 = fields.Selection(
        selection=PLATE_LETTER_SELECTION,
        string="Letter 3",
    )
    plate_numbers_ar = fields.Char(
        string="Arabic Numbers", help="The numeric part in Arabic numerals (Hindi).")
    plate_numbers = fields.Char(
        string="Western Arabic Numbers", help="The numeric part in Western Arabic numerals.")
    vin_sn = fields.Char(required=True)

    license_plate = fields.Char(
        compute="_compute_license_plate", store=True, tracking=True)

    unverified_model_name = fields.Char(
        copy=False, readonly=True, help="Useful when the portal customer car brand doesn't exist in the system."
    )
    display_name = fields.Char(compute="_compute_display_name")

    @api.model
    def create(self, vals):
        vals = dict(vals)
        self._sync_plate_letter_vals(vals)
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

    def write(self, vals):
        vals = dict(vals)
        letter_part_keys = ("plate_letter_1", "plate_letter_2", "plate_letter_3")
        has_letter_parts = any(key in vals for key in letter_part_keys)
        has_plate_letters = "plate_letters" in vals

        if has_letter_parts and not has_plate_letters:
            if all(key in vals for key in letter_part_keys) or len(self) == 1:
                merged = dict(vals)
                if len(self) == 1 and not all(key in vals for key in letter_part_keys):
                    vehicle = self
                    merged.update({
                        "plate_letter_1": vals.get(
                            "plate_letter_1", vehicle.plate_letter_1
                        ),
                        "plate_letter_2": vals.get(
                            "plate_letter_2", vehicle.plate_letter_2
                        ),
                        "plate_letter_3": vals.get(
                            "plate_letter_3", vehicle.plate_letter_3
                        ),
                    })
                self._sync_plate_letter_vals(merged)
                return super().write(merged)
            for vehicle in self:
                merged = {
                    "plate_letter_1": vals.get(
                        "plate_letter_1", vehicle.plate_letter_1
                    ),
                    "plate_letter_2": vals.get(
                        "plate_letter_2", vehicle.plate_letter_2
                    ),
                    "plate_letter_3": vals.get(
                        "plate_letter_3", vehicle.plate_letter_3
                    ),
                }
                self._sync_plate_letter_vals(merged)
                super(FleetVehicle, vehicle).write({**vals, **merged})
            return True

        if has_plate_letters or has_letter_parts:
            self._sync_plate_letter_vals(vals)
        return super().write(vals)

    @api.model
    def _split_plate_letters(self, plate_letters):
        """Return selection values for the three latin plate letters."""
        allowed = set(EN_TO_AR_LETTERS)
        raw = (plate_letters or "").upper().replace(" ", "")
        parts = []
        for index in range(3):
            char = raw[index] if index < len(raw) else False
            parts.append(char if char in allowed else False)
        return parts

    @api.model
    def _join_plate_letters(self, letter_1, letter_2, letter_3):
        letters = [letter for letter in (letter_1, letter_2, letter_3) if letter]
        return " ".join(letters) or False

    @api.model
    def _sync_plate_letter_vals(self, vals):
        """Keep plate_letters and the three selections aligned in create/write vals."""
        if any(key in vals for key in ("plate_letter_1", "plate_letter_2", "plate_letter_3")):
            letters = self._join_plate_letters(
                vals.get("plate_letter_1"),
                vals.get("plate_letter_2"),
                vals.get("plate_letter_3"),
            )
            vals["plate_letters"] = letters
            if "plate_letters_ar" not in vals:
                vals["plate_letters_ar"] = (
                    _convert_en_letters_to_ar(letters) if letters else False
                )
        elif "plate_letters" in vals:
            letter_1, letter_2, letter_3 = self._split_plate_letters(vals.get("plate_letters"))
            vals["plate_letter_1"] = letter_1
            vals["plate_letter_2"] = letter_2
            vals["plate_letter_3"] = letter_3
            if vals.get("plate_letters") and "plate_letters_ar" not in vals:
                vals["plate_letters_ar"] = _convert_en_letters_to_ar(vals["plate_letters"])
        return vals


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

    @api.onchange("partner_id")
    def _onchange_partner_id_plate_fields(self):
        """Clear Saudi-only plate parts when the owner is not Saudi."""
        code = self.partner_id.country_id.code
        if code and code != "SA":
            self.plate_letters = False
            self.plate_letters_ar = False
            self.plate_letter_1 = False
            self.plate_letter_2 = False
            self.plate_letter_3 = False
            self.plate_numbers_ar = False

    def _is_saudi_plate_owner(self):
        """Saudi layout when country is SA or not set yet."""
        code = self.partner_id.country_id.code if self.partner_id else False
        return not code or code == "SA"

    @api.onchange("plate_letter_1", "plate_letter_2", "plate_letter_3")
    def _onchange_plate_letter_parts(self):
        """Mirror selected letters into the main latin/arabic plate fields."""
        if self.env.context.get("skip_plate_convert"):
            return
        letters = self._join_plate_letters(
            self.plate_letter_1, self.plate_letter_2, self.plate_letter_3
        )
        self.plate_letters = letters
        if self._is_saudi_plate_owner():
            self.plate_letters_ar = (
                _convert_en_letters_to_ar(letters) if letters else False
            )

    @api.onchange("plate_letters_ar")
    def _onchange_plate_letters_ar(self):
        if self.env.context.get("skip_plate_convert") or not self._is_saudi_plate_owner():
            return
        self.plate_letters = _convert_ar_letters_to_en(self.plate_letters_ar or "")
        letter_1, letter_2, letter_3 = self._split_plate_letters(self.plate_letters)
        self.plate_letter_1 = letter_1
        self.plate_letter_2 = letter_2
        self.plate_letter_3 = letter_3

    @api.onchange("plate_letters")
    def _onchange_plate_letters(self):
        if self.env.context.get("skip_plate_convert"):
            return
        letter_1, letter_2, letter_3 = self._split_plate_letters(self.plate_letters)
        self.with_context(skip_plate_convert=True).update({
            "plate_letter_1": letter_1,
            "plate_letter_2": letter_2,
            "plate_letter_3": letter_3,
        })
        if not self._is_saudi_plate_owner():
            return
        converted = _convert_en_letters_to_ar(self.plate_letters or "")
        current_en_from_ar = _convert_ar_letters_to_en(self.plate_letters_ar or "")
        if (self.plate_letters or "") != current_en_from_ar:
            self.with_context(skip_plate_convert=True).update({
                "plate_letters_ar": converted,
            })

    @api.onchange("plate_numbers_ar")
    def _onchange_plate_numbers_ar(self):
        if self.env.context.get("skip_plate_convert") or not self._is_saudi_plate_owner():
            return
        self.plate_numbers = _convert_ar_digits_to_en(self.plate_numbers_ar or "")

    @api.onchange("plate_numbers")
    def _onchange_plate_numbers(self):
        if self.env.context.get("skip_plate_convert") or not self._is_saudi_plate_owner():
            return
        converted = _convert_en_digits_to_ar(self.plate_numbers or "")
        current_en_from_ar = _convert_ar_digits_to_en(self.plate_numbers_ar or "")
        if (self.plate_numbers or "") != current_en_from_ar:
            self.with_context(skip_plate_convert=True).update({
                "plate_numbers_ar": converted,
            })

    @api.constrains("vin_sn")
    def _check_vin_sn(self):
        for vehicle in self:
            vin = (vehicle.vin_sn or "").strip()
            if not vin:
                raise ValidationError(_("The Chassis Number is required."))
            if not (8 <= len(vin) <= 17):
                raise ValidationError(_(
                    "The Chassis Number must be between 8 and 17 characters."
                ))
            if not re.fullmatch(r"[A-Za-z0-9]+", vin):
                raise ValidationError(_(
                    "The Chassis Number may only contain English letters and numbers."
                ))

    @api.depends(
        "plate_letters_ar",
        "plate_letters",
        "plate_numbers_ar",
        "plate_numbers",
        "partner_id.country_id.code",
    )
    def _compute_license_plate(self):
        for vehicle in self:
            country_code = vehicle.partner_id.country_id.code
            # Non-Saudi (and website "Others"): plate stored in plate_numbers only.
            if country_code and country_code != "SA":
                vehicle.license_plate = vehicle.plate_numbers or ""
                continue
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

    @api.depends(
        "plate_letters_ar",
        "plate_letters",
        "plate_numbers_ar",
        "plate_numbers",
        "partner_id.country_id.code",
        "brand_id.name",
        "model_id.name",
    )
    @api.depends_context("lang")
    def _compute_display_name(self):
        """Compute vehicle display name based on user language and plate details."""
        for vehicle in self:
            country_code = vehicle.partner_id.country_id.code
            if country_code and country_code != "SA":
                plate = vehicle.plate_numbers or vehicle.license_plate or ""
            else:
                lang = vehicle.env.context.get("lang", "en_US")
                plate_letters = (
                    vehicle.plate_letters_ar
                    if lang.startswith("ar")
                    else vehicle.plate_letters
                )
                plate_numbers = (
                    vehicle.plate_numbers_ar
                    if lang.startswith("ar")
                    else vehicle.plate_numbers
                )
                plate = f"{plate_numbers or ''}-{plate_letters or ''}".strip("-")
            vehicle.display_name = (
                f"{vehicle.brand_id.name or ''} / {vehicle.model_id.name or ''} / "
                f"{plate or _('No Plate')}"
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
