from odoo import fields, models


class PortalStatistic(models.Model):
    _name = "portal.statistic"
    _description = "Portal Statistic"

    active = fields.Boolean(default=True)

    name = fields.Char(required=True, translate=True)
    value = fields.Char(required=True, translate=True)
