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
        default=False,
        help="When checked, this color is sent to the website. Uncheck to use the default color. Only one theme can be current.",
    )

    def init(self):
        self.env.cr.execute(
            """
            WITH keep AS (
                SELECT id
                FROM portal_theme
                WHERE is_current = true
                ORDER BY write_date DESC NULLS LAST, id DESC
                LIMIT 1
            )
            UPDATE portal_theme
               SET is_current = false
             WHERE is_current = true
               AND id NOT IN (SELECT id FROM keep)
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS portal_theme_unique_current
                ON portal_theme (is_current)
             WHERE is_current = true
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get("is_current") for vals in vals_list):
            last_current_idx = max(
                i for i, vals in enumerate(vals_list) if vals.get("is_current")
            )
            for i, vals in enumerate(vals_list):
                if i != last_current_idx and vals.get("is_current"):
                    vals["is_current"] = False
            self.search([("is_current", "=", True)]).with_context(
                skip_current_theme_check=True
            ).write({"is_current": False})
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("skip_current_theme_check"):
            return super().write(vals)

        if vals.get("is_current"):
            keep = self[-1]
            others = self.search([("is_current", "=", True), ("id", "!=", keep.id)])
            if others:
                others.with_context(skip_current_theme_check=True).write(
                    {"is_current": False}
                )
            if len(self) > 1:
                other_in_self = self - keep
                if other_in_self:
                    other_in_self.with_context(skip_current_theme_check=True).write(
                        dict(vals, is_current=False)
                    )
                return keep.with_context(skip_current_theme_check=True).write(vals)

        return super().write(vals)

    @api.constrains("is_current")
    def _check_only_one_current_theme(self):
        if self.search_count([("is_current", "=", True)]) > 1:
            raise ValidationError(_("Only one theme can be marked as Current."))

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
