from odoo import fields, models


class FleetVehicleModel(models.Model):
    _inherit = "fleet.vehicle.model"

    size = fields.Selection([("small", "Small"), ("medium", "Medium"), ("large", "Large"), ("x-large", "Very large")])
    # replace field model_year == char by a model
    model_year = fields.Many2one("car.model.year")


class CarModelYear(models.Model):
    _name = "car.model.year"
    _description = "Model year"
    _rec_name = "year"

    year = fields.Integer()

    _sql_constraints = [
        ("unique_year", "unique(year)", "The model year must be unique"),
    ]
