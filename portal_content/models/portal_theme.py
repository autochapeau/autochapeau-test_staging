import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PortalTheme(models.Model):
    _name = "portal.theme"
    _description = "Portal Theme Color"
    _order = "date_start desc, id desc"

    active = fields.Boolean(default=True)
    name = fields.Char(string="Occasion", required=True, translate=True)
    color = fields.Char(string="Color", required=True, default="#760260")
    date_start = fields.Date(string="Start Date", required=True)
    date_end = fields.Date(string="End Date", required=True)
    is_current = fields.Boolean(
        string="Current",
        compute="_compute_is_current",
        search="_search_is_current",
    )

    @api.depends("date_start", "date_end", "active")
    def _compute_is_current(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_current = bool(
                rec.active
                and rec.date_start
                and rec.date_end
                and rec.date_start <= today <= rec.date_end
            )

    def _search_is_current(self, operator, value):
        today = fields.Date.context_today(self)
        domain = [
            ("active", "=", True),
            ("date_start", "<=", today),
            ("date_end", ">=", today),
        ]
        if (operator == "=" and value) or (operator == "!=" and not value):
            return domain
        return ["!"] + domain

    @api.constrains("color")
    def _check_color(self):
        for rec in self:
            if rec.color and not re.fullmatch(r"#[0-9A-Fa-f]{6}", rec.color):
                raise ValidationError(_("Color must be a hex code like #760260"))

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError(_("End date must be after start date."))
            overlap = self.search(
                [
                    ("id", "!=", rec.id),
                    ("active", "=", True),
                    ("date_start", "<=", rec.date_end),
                    ("date_end", ">=", rec.date_start),
                ],
                limit=1,
            )
            if overlap:
                raise ValidationError(
                    _("This period overlaps with '%s'. Only one theme can be active at a time.")
                    % overlap.name
                )
