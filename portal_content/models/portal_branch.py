from odoo import fields, models


class PortalBranch(models.Model):
    _name = "portal.branch"
    _inherit = "image.mixin"
    _description = "Portal Branch"
    _order = "sequence,id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    address = fields.Text(translate=True)
    map_url = fields.Char()
