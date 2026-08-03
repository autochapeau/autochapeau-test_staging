from odoo import api, fields, models


class CarWorkorderService(models.Model):
    _inherit = "car.workorder.service"

    is_window_tinting = fields.Boolean(
        related="product_id.product_tmpl_id.is_window_tinting",
        string="Window Tinting Service",
        readonly=True,
    )
    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Sale Order Line",
        compute="_compute_sale_line_id",
        store=False,
    )
    tint_detail_ids = fields.One2many(
        related="sale_line_id.tint_detail_ids",
        string="Tint Details",
        readonly=True,
    )
    tint_details_summary = fields.Char(
        related="sale_line_id.tint_details_summary",
        string="Tint Details Summary",
        readonly=True,
    )

    @api.depends(
        "product_id",
        "workorder_id",
        "workorder_id.sale_order_id",
        "workorder_id.sale_order_id.order_line",
        "workorder_id.sale_order_id.order_line.product_id",
        "workorder_id.sale_order_id.order_line.is_window_tinting",
    )
    def _compute_sale_line_id(self):
        for service in self:
            sale = service.workorder_id.sale_order_id
            if not sale or not service.product_id:
                service.sale_line_id = False
                continue
            lines = sale.order_line.filtered(
                lambda line: (
                    not line.display_type
                    and line.product_id == service.product_id
                    and line.is_window_tinting
                )
            )
            service.sale_line_id = lines[:1]
