from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    gender = fields.Selection(
        [
            ("male", "Male"),
            ("female", "Female"),
        ],
        string="Gender",
    )
    nationality_id = fields.Many2one(
        "res.country",
        string="Nationality",
        ondelete="restrict",
    )
    country_id = fields.Many2one(default=lambda self: self._default_saudi_country_id())

    @api.model
    def _default_saudi_country_id(self):
        return self.env["res.country"].search([("code", "=", "SA")], limit=1)

    def _requires_company_extra_fields(self):
        self.ensure_one()
        return self.is_company and not self.parent_id

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "country_id" in fields_list and not values.get("country_id"):
            country = self._default_saudi_country_id()
            if country:
                values["country_id"] = country.id
        return values

    @api.onchange("company_type")
    def _onchange_company_type_clear_gender(self):
        if self.company_type == "company":
            self.gender = False

    @api.onchange("country_id")
    def _onchange_country_id_clear_mobile(self):
        if not self.country_id:
            self.mobile = False

    @api.constrains("mobile", "country_id")
    def _check_mobile_requires_country(self):
        for partner in self:
            if partner.mobile and not partner.country_id:
                raise ValidationError(_(
                    "Please select the country before entering the mobile number."
                ))

    @api.constrains("company_type", "is_company", "parent_id", "street", "vat", "company_registry")
    def _check_company_required_fields(self):
        for partner in self:
            if not partner._requires_company_extra_fields():
                continue
            missing = []
            if not (partner.street or "").strip():
                missing.append(_("National Address"))
            if not (partner.vat or "").strip():
                missing.append(_("Tax ID"))
            if not (partner.company_registry or "").strip():
                missing.append(_("Commercial Registration (CR)"))
            if missing:
                raise ValidationError(_(
                    "The following fields are required for a company: %s."
                ) % ", ".join(missing))

    @api.model_create_multi
    def create(self, vals_list):
        country = self._default_saudi_country_id()
        for vals in vals_list:
            if not vals.get("country_id") and country:
                vals["country_id"] = country.id
            if vals.get("company_type") == "company" or vals.get("is_company"):
                vals["gender"] = False
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("company_type") == "company" or vals.get("is_company"):
            vals["gender"] = False
        if "country_id" in vals and not vals.get("country_id"):
            vals.setdefault("mobile", False)
        return super().write(vals)
