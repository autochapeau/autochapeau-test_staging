from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrderLineTintDetail(models.Model):
    _name = "sale.order.line.tint.detail"
    _description = "Sale Order Line Tint Detail"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)

    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sale Order Line",
        required=True,
        ondelete="cascade",
        index=True,
    )

    glass_type_id = fields.Many2one(
        comodel_name="window.tint.glass.type",
        string="Glass Type",
        required=True,
        ondelete="restrict",
    )

    tint_percentage_id = fields.Many2one(
        comodel_name="window.tint.percentage",
        string="Tint Percentage",
        required=True,
        ondelete="restrict",
    )

    note = fields.Char(string="Note")

    available_glass_type_ids = fields.Many2many(
        comodel_name="window.tint.glass.type",
        compute="_compute_available_values",
        string="Available Glass Types",
    )

    available_tint_percentage_ids = fields.Many2many(
        comodel_name="window.tint.percentage",
        compute="_compute_available_values",
        string="Available Tint Percentages",
    )

    @api.depends(
        "sale_order_line_id.product_id",
        "sale_order_line_id.product_id.product_tmpl_id.allowed_glass_type_ids",
        "sale_order_line_id.product_id.product_tmpl_id.allowed_tint_percentage_ids",
    )
    def _compute_available_values(self):
        all_glass_types = self.env["window.tint.glass.type"].search(
            [("active", "=", True)]
        )
        all_percentages = self.env["window.tint.percentage"].search(
            [("active", "=", True)]
        )

        for detail in self:
            template = detail.sale_order_line_id.product_id.product_tmpl_id
            detail.available_glass_type_ids = (
                template.allowed_glass_type_ids or all_glass_types
            )
            detail.available_tint_percentage_ids = (
                template.allowed_tint_percentage_ids or all_percentages
            )

    @api.constrains(
        "sale_order_line_id",
        "glass_type_id",
        "tint_percentage_id",
    )
    def _check_allowed_values(self):
        for detail in self:
            line = detail.sale_order_line_id
            if not line or not line.product_id:
                continue

            if not line.is_window_tinting:
                raise ValidationError(
                    _("Tint details can only be added to window tinting products.")
                )

            if detail.glass_type_id not in detail.available_glass_type_ids:
                raise ValidationError(
                    _("The selected glass type is not allowed for this product.")
                )

            if (
                detail.tint_percentage_id
                not in detail.available_tint_percentage_ids
            ):
                raise ValidationError(
                    _(
                        "The selected tint percentage is not allowed "
                        "for this product."
                    )
                )

    _sql_constraints = [
        (
            "sale_line_glass_type_unique",
            "unique(sale_order_line_id, glass_type_id)",
            "The same glass type cannot be added twice to one sale order line.",
        ),
    ]
