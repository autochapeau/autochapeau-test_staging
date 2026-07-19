from odoo import fields, models


class PortalPartner(models.Model):
    _name = "portal.partner"
    _inherit = "image.mixin"
    _description = "Portal Partner"
    _order = "sequence,id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
