from odoo import fields, models


class PortalPatner(models.Model):
    _name = "portal.loyalty.program"
    _inherit = "image.mixin"
    _description = "Portal Loyalty Program"

    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
