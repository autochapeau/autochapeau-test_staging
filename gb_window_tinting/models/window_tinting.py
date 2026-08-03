from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WindowTintGlassType(models.Model):
    _name = "window.tint.glass.type"
    _description = "Window Tint Glass Type"
    _order = "sequence, name, id"

    name = fields.Char(
        string="Glass Type",
        required=True,
        translate=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "window_tint_glass_type_name_unique",
            "unique(name)",
            "The glass type must be unique.",
        ),
    ]


class WindowTintPercentage(models.Model):
    _name = "window.tint.percentage"
    _description = "Window Tint Percentage"
    _order = "percentage, name, id"

    name = fields.Char(
        string="Name",
        required=True,
        help="Example: 50%",
    )
    percentage = fields.Float(
        string="Percentage",
        required=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "window_tint_percentage_unique",
            "unique(percentage)",
            "The tint percentage must be unique.",
        ),
    ]

    @api.constrains("percentage")
    def _check_percentage(self):
        for record in self:
            if record.percentage < 0 or record.percentage > 100:
                raise ValidationError(
                    _("Tint percentage must be between 0 and 100.")
                )
