from odoo import _, api, models
from odoo.exceptions import AccessError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _own_contact_restricted(self):
        return (
            not self.env.su
            and self.env.user.has_group("own_contact.group_own_contact")
            and not self.env.user.has_group("own_contact.group_all_contacts")
        )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "user_id" in fields_list:
            if self._own_contact_restricted():
                values["user_id"] = self.env.uid
            elif self.env.user.has_group("own_contact.group_all_contacts"):
                values.setdefault("user_id", self.env.uid)
                if not values["user_id"]:
                    values["user_id"] = self.env.uid
        return values

    @api.model_create_multi
    def create(self, vals_list):
        restricted = self._own_contact_restricted()
        managed = restricted or self.env.user.has_group("own_contact.group_all_contacts")
        if managed and not self.env.su:
            vals_list = [dict(values) for values in vals_list]
            for values in vals_list:
                if restricted or not values.get("user_id"):
                    values["user_id"] = self.env.uid
        return super().create(vals_list)

    def write(self, values):
        if (
            "user_id" in values
            and self._own_contact_restricted()
            and values["user_id"] != self.env.uid
        ):
            raise AccessError(_("Only a contact manager can assign contacts to another salesperson."))
        return super().write(values)
