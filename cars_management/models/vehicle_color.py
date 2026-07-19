from odoo import fields, models


class VehicleColor(models.Model):
    _name = "vehicle.color"
    _description = "Vehicle color"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()
