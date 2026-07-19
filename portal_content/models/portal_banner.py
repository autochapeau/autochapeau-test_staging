from odoo import fields, models


class PortalBanner(models.Model):
    _name = "portal.banner"
    _description = "Portal Banner"
    _rec_name = "first_title"

    active = fields.Boolean(default=True)

    first_title = fields.Char(required=True, translate=True)
    second_title = fields.Char(translate=True)
    url = fields.Char()
