from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    workorder_id = fields.Many2one(
        "car.work.order",
        compute="_compute_window_tinting_info",
        string="Work Order",
    )
    is_window_tinting = fields.Boolean(
        compute="_compute_window_tinting_info",
        string="Window Tinting Service",
    )
    tint_detail_ids = fields.Many2many(
        "sale.order.line.tint.detail",
        compute="_compute_window_tinting_info",
        compute_sudo=True,
        string="Tint Details",
    )
    tint_details_summary = fields.Char(
        compute="_compute_window_tinting_info",
        compute_sudo=True,
        string="Tint Details Summary",
    )

    @api.depends("origin")
    def _compute_window_tinting_info(self):
        WorkOrder = self.env["car.work.order"].sudo()
        workorders = WorkOrder.search([("picking_id", "in", self.ids)])
        workorder_by_picking = {workorder.picking_id.id: workorder for workorder in workorders}

        for picking in self:
            workorder = workorder_by_picking.get(picking.id)
            if not workorder:
                picking.workorder_id = False
                picking.is_window_tinting = False
                picking.tint_detail_ids = False
                picking.tint_details_summary = False
                continue

            picking.workorder_id = workorder.id
            sale = workorder.sale_order_id
            lines = sale.order_line.filtered(
                lambda line: (
                    not line.display_type
                    and line.is_window_tinting
                    and line.tint_detail_ids
                )
            )
            picking.is_window_tinting = bool(lines)
            picking.tint_detail_ids = lines.mapped("tint_detail_ids")
            picking.tint_details_summary = " | ".join(
                summary for summary in lines.mapped("tint_details_summary") if summary
            )
