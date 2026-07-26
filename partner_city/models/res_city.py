from odoo import fields, models


class ResCity(models.Model):
    _name = "res.city"
    _description = "City"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
