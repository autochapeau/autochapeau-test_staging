from odoo import fields, models


class PortalPrivacyPolicy(models.Model):
    _name = "portal.privacy.policy"
    _description = "Portal Privacy Policy"

    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
