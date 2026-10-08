from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class MaintenanceClaimWizard(models.TransientModel):
    _name = "maintenance.claim.wizard"
    _description = "Maintenance Request Wizard"

    sale_order_id = fields.Many2one("sale.order", required=True, readonly=True)
    problem_location = fields.Text(string="Where is the problem?", required=True)
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

    def _prepare_part_commands(self, line, product, company):
        """Window tinting uses the glasses sold on this line. Other services use the BOM."""
        if line.is_window_tinting:
            details = line.tint_detail_ids
            if not details:
                raise UserError(_(
                    "This tinting service has no glass details on the original order."
                ))
            service = product.with_company(company)
            return [
                Command.create({
                    "product_id": service.id,
                    "quantity": 1.0,
                    "unit_cost": service.standard_price,
                    "include": False,
                    "glass_type_id": detail.glass_type_id.id,
                    "tint_percentage_id": detail.tint_percentage_id.id,
                    "origin_tint_detail_id": detail.id,
                })
                for detail in details
            ]
        part_commands = []
        for bom in product.bom_ids:
            part = bom.product_id.with_company(company)
            part_commands.append(Command.create({
                "product_id": part.id,
                "quantity": bom.quantity or 1.0,
                "unit_cost": part.standard_price,
                "include": False,
            }))
        if not part_commands:
            service = product.with_company(company)
            part_commands.append(Command.create({
                "product_id": service.id,
                "quantity": 1.0,
                "unit_cost": service.standard_price,
                "include": True,
            }))
        return part_commands

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
        claim = self.env["maintenance.claim"].create({
            "origin_sale_id": order.id,
            "origin_sale_line_id": line.id,
            "problem_location": (self.problem_location or "").strip(),
            "part_ids": part_commands,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Maintenance Quality"),
            "res_model": "maintenance.claim",
            "view_mode": "form",
            "res_id": claim.id,
            "target": "current",
        }
