from odoo import fields, models


class CarCheckItem(models.Model):
    _name = "car.check.item"
    _description = "Car check Item"

    name = fields.Char(translate=True, required=True)
    active = fields.Boolean(default=True)
    check_in = fields.Boolean(
        string="Check-in", default=True, help="Show this item during check-in")
    check_out = fields.Boolean(
        string="Check-out", default=True, help="Show this item during check-out")
    required = fields.Boolean(string="Required", default=False,
                              help="This item is required if checked, otherwise optional.")
