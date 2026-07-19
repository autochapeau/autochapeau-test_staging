from odoo import fields, models


class PortalTermsConditions(models.Model):
    _name = "portal.terms.conditions"
    _description = "Portal Terms Conditions"

    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
