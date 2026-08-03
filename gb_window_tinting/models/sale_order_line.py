from odoo import api, fields, models, _


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_window_tinting = fields.Boolean(
        related="product_id.product_tmpl_id.is_window_tinting",
        string="Window Tinting Service",
        readonly=True,
    )

    tint_detail_ids = fields.One2many(
        comodel_name="sale.order.line.tint.detail",
        inverse_name="sale_order_line_id",
        string="Tint Details",
        copy=True,
    )

    tint_detail_count = fields.Integer(
        compute="_compute_tint_detail_count",
        string="Tint Detail Count",
    )

    tint_details_summary = fields.Char(
        compute="_compute_tint_details_summary",
        string="Tint Details",
    )

    @api.depends("tint_detail_ids")
    def _compute_tint_detail_count(self):
        for line in self:
            line.tint_detail_count = len(line.tint_detail_ids)

    @api.depends(
        "tint_detail_ids",
        "tint_detail_ids.glass_type_id",
        "tint_detail_ids.tint_percentage_id",
    )
    def _compute_tint_details_summary(self):
        for line in self:
            parts = []
            for detail in line.tint_detail_ids.sorted(
                key=lambda record: (record.sequence, record.id)
            ):
                if detail.glass_type_id and detail.tint_percentage_id:
                    parts.append(
                        "%s: %s"
                        % (
                            detail.glass_type_id.display_name,
                            detail.tint_percentage_id.display_name,
                        )
                    )
            line.tint_details_summary = " | ".join(parts)

    @api.onchange("product_id")
    def _onchange_product_clear_tint_details(self):
        for line in self:
            if not line.is_window_tinting:
                line.tint_detail_ids = [(5, 0, 0)]

    def action_open_tint_details(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Tint Details"),
            "res_model": "sale.order.line",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "gb_window_tinting.view_sale_order_line_tint_details_form"
            ).id,
            "target": "new",
        }

    def action_generate_tint_details(self):
        glass_model = self.env["window.tint.glass.type"]

        for line in self:
            if not line.is_window_tinting:
                continue

            template = line.product_id.product_tmpl_id
            glass_types = (
                template.allowed_glass_type_ids
                or glass_model.search([("active", "=", True)])
            )

            existing_glass_types = line.tint_detail_ids.mapped("glass_type_id")
            commands = []

            for glass_type in glass_types - existing_glass_types:
                commands.append(
                    (
                        0,
                        0,
                        {
                            "sequence": glass_type.sequence,
                            "glass_type_id": glass_type.id,
                        },
                    )
                )

            if commands:
                line.write({"tint_detail_ids": commands})

        return True
