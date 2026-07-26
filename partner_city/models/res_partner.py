from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    city_id = fields.Many2one(
        "res.city",
        string="City",
        ondelete="restrict",
    )

    @api.onchange("city_id")
    def _onchange_city_id(self):
        self.city = self.city_id.name if self.city_id else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_city_from_city_id(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._sync_city_from_city_id(vals)
        return super().write(vals)

    @api.model
    def _sync_city_from_city_id(self, vals):
        if "city_id" not in vals:
            return
        city_id = vals.get("city_id")
        if city_id:
            city = self.env["res.city"].browse(city_id)
            vals["city"] = city.name
        else:
            vals["city"] = False
