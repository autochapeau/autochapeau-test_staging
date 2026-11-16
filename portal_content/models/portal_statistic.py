from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PortalStatistic(models.Model):
    _name = "portal.statistic"
    _description = "Portal Statistic"

    active = fields.Boolean(default=True)

    name = fields.Char(required=True, translate=True)
    value = fields.Char(required=True, translate=True)
    metric = fields.Selection([
        ("manual", "Manual value"), ("cars", "Serviced Cars"),
        ("customers", "Served Customers"), ("services", "Completed Services"),
    ], default="manual", required=True)
    opening_value = fields.Integer(string="Historical Opening Balance", default=0)
    count_from = fields.Datetime(string="Count Completions From", default=fields.Datetime.now)
    car_count_mode = fields.Selection([
        ("unique", "Each car once"), ("visits", "Each work order / visit"),
    ], default="unique", required=True)

    @api.constrains("opening_value", "metric", "count_from")
    def _check_counter_settings(self):
        for counter in self:
            if counter.opening_value < 0:
                raise ValidationError(_("The opening balance cannot be negative."))
            if counter.metric != "manual" and not counter.count_from:
                raise ValidationError(_("Set the starting date for the automatic counter."))

    def _website_value(self):
        self.ensure_one()
        return self.value
