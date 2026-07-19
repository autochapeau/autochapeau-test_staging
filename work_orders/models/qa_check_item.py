from odoo import fields, models


class QACheckItem(models.Model):
    _name = "qa.check.item"
    _description = "QA Check Item"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
