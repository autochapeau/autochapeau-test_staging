from odoo import fields, models


class PortalTestimony(models.Model):
    _name = "portal.testimony"
    _inherit = "image.mixin"
    _description = "Portal Testimony"
    _order = "sequence,id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    date = fields.Date()
