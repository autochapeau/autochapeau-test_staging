from odoo import fields, models


class PortalAboutus(models.Model):
    _name = "portal.aboutus"
    _inherit = "image.mixin"
    _description = "Portal About us"

    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
