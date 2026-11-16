from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from ..models.maintenance_claim import _SOURCE_TOKEN


class MaintenanceClaimWizard(models.TransientModel):
    _name = "maintenance.claim.wizard"
    _description = "Maintenance Request Wizard"

    sale_order_id = fields.Many2one("sale.order", required=True, readonly=True)
    problem_location = fields.Text(string="Where is the problem?", required=False)
    service_line_id = fields.Many2one(
        "sale.order.line",
        string="Service",
        required=True,
        domain="[('id', 'in', available_line_ids)]",
    )
    available_line_ids = fields.Many2many(
        "sale.order.line",
        compute="_compute_available_line_ids",
    )

    @api.depends("sale_order_id", "sale_order_id.order_line", "sale_order_id.order_line.product_id")
    def _compute_available_line_ids(self):
        for wizard in self:
            lines = wizard.sale_order_id.order_line.filtered(
                lambda line: not line.display_type
                and line.product_id
                and line.product_id.detailed_type == "service"
            )
            wizard.available_line_ids = lines

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        if self.service_line_id and self.service_line_id not in self.available_line_ids:
            self.service_line_id = False

    source_task_id = fields.Many2one(
        "car.workorder.service", string="Original Work Order Service", required=True,
        domain="[('id', 'in', available_task_ids)]",
    )
    available_task_ids = fields.Many2many("car.workorder.service", compute="_compute_sources")
    available_part_ids = fields.Many2many("car.part", compute="_compute_sources")
    selected_part_ids = fields.Many2many(
        "car.part", string="Parts to Repair", required=True,
        domain="[('id', 'in', available_part_ids)]",
    )

    @api.depends("sale_order_id", "service_line_id", "source_task_id")
    def _compute_sources(self):
        for wizard in self:
            wizard.available_task_ids = wizard._source_tasks()
            wizard.available_part_ids = wizard._issued_materials().part_id

    def _source_tasks(self):
        self.ensure_one()
        order = self.sale_order_id
        if not order or not self.service_line_id:
            return self.env["car.workorder.service"]
        # Check the original sale with the requester's permissions before the
        # controlled read of work order/material records.
        order.check_access_rights("read")
        order.check_access_rule("read")
        return self.env["car.workorder.service"].sudo().search([
            ("product_id", "=", self.service_line_id.product_id.id),
            ("workorder_id.company_id", "=", order.company_id.id),
            ("materials_issued", "=", True),
            "|", ("workorder_id.sale_order_id", "=", order.id),
            ("workorder_id.appointment_id.sale_order_id", "=", order.id),
        ])

    def _issued_materials(self):
        self.ensure_one()
        return self.source_task_id.sudo().workorder_id.product_ids.filtered(
            lambda row: row.source_task_id == self.source_task_id
            and row.material_move_id.state == "done" and row.part_id
            and row.quantity > 0
        )

    @api.onchange("service_line_id")
    def _onchange_service_line_id(self):
        tasks = self._source_tasks()
        self.source_task_id = tasks if len(tasks) == 1 else False
        self.selected_part_ids = False

    @api.onchange("source_task_id")
    def _onchange_source_task_id(self):
        self.selected_part_ids = False

    def _prepare_part_commands(self, line, product, company):
        if self.source_task_id not in self._source_tasks():
            raise UserError(_("Select an issued service from this order's original work order."))
        # A task cannot disambiguate duplicate sale lines of the same variant.
        matching = self.sale_order_id.order_line.filtered(
            lambda item: not item.display_type and item.product_id == product
        )
        if len(matching) != 1:
            raise UserError(_("This order has repeated service lines. Review the original work order service mapping first."))
        materials = self._issued_materials()
        if not self.selected_part_ids or self.selected_part_ids - materials.part_id:
            raise UserError(_("Select one or more parts with actual issued materials from this service."))
        commands = []
        for row in materials.filtered(lambda item: item.part_id in self.selected_part_ids):
            move = row.material_move_id.sudo()
            layers = move.stock_valuation_layer_ids
            qty = abs(sum(layers.mapped("quantity")))
            if not layers or not qty:
                raise UserError(_("The issued material %s has no stock valuation. Review its original delivery; estimated costs are not used.") % row.product_id.display_name)
            actual_qty = move.product_uom._compute_quantity(move.quantity, row.product_id.uom_id)
            tint_vals = {}
            if line.is_window_tinting:
                glass = row.part_id.maintenance_glass_type_id
                detail = line.tint_detail_ids.filtered(lambda detail: detail.glass_type_id == glass)
                if not glass or len(detail) != 1:
                    raise UserError(_("Map vehicle part %s to its original tint glass type in Vehicle Parts before requesting maintenance.") % row.part_id.display_name)
                tint_vals = {"glass_type_id": glass.id, "tint_percentage_id": detail.tint_percentage_id.id,
                             "origin_tint_detail_id": detail.id}
            commands.append(Command.create({
                **tint_vals,
                "product_id": row.product_id.id, "quantity": actual_qty,
                "unit_cost": abs(sum(layers.mapped("value"))) / qty,
                "include": True, "source_material_id": row.id,
            }))
        return commands

    def action_confirm(self):
        self.ensure_one()
        order = self.sale_order_id
        line = self.service_line_id
        if not order or order.state not in ("sale", "done"):
            raise UserError(_("Maintenance can be requested from a confirmed order."))
        if not line or line.order_id != order or line.product_id.detailed_type != "service":
            raise UserError(_("Select a service from this order."))
        product = line.product_id
        company = order.company_id
        part_commands = self._prepare_part_commands(line, product, company)
        claim = self.env["maintenance.claim"].with_context(maintenance_source_token=_SOURCE_TOKEN).create({
            "origin_sale_id": order.id,
            "origin_sale_line_id": line.id,
            "problem_location": (self.problem_location or ", ".join(self.selected_part_ids.mapped("name"))).strip(),
            "part_ids": part_commands,
            "source_task_id": self.source_task_id.id,
            "sale_order_id": False,
            "appointment_id": False,
            "move_id": False,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Maintenance Quality"),
            "res_model": "maintenance.claim",
            "view_mode": "form",
            "res_id": claim.id,
            "target": "current",
        }
