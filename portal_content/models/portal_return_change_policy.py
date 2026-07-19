from odoo import fields, models


class PortalReturnChangePolicy(models.Model):
    _name = "portal.return.change.policy"
    _description = "Portal Return Change Policy"

    active = fields.Boolean(default=True)
    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
