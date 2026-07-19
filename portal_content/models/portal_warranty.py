from odoo import fields, models


class PortalWarranty(models.Model):
    _name = "portal.warranty"
    _description = "Portal Warranty"

    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    details = fields.Html(translate=True)
