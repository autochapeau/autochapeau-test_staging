from odoo import fields, models


class CommissionCategory(models.Model):
    _name = "commission.category"
    _description = "Commission Category"
    _order = "sequence,id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(required=True)
