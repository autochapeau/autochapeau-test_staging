from odoo import fields, models


class ResCity(models.Model):
    _name = "res.city"
    _description = "City"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    country_id = fields.Many2one(
        "res.country",
        string="Country",
        ondelete="restrict",
        index=True,
    )
    active = fields.Boolean(default=True)
