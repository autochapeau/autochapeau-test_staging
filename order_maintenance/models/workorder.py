from odoo import _, api, fields, models
from odoo.exceptions import UserError
from .maintenance_claim import _SOURCE_TOKEN


class WorkOrder(models.Model):
    _inherit = "car.work.order"

    def _get_service_material_components(self, task):
        components = super()._get_service_material_components(task)
        claim = self._get_linked_sale_order().maintenance_claim_id
        # Repairs snapshot the selected original issued materials, not today's BOM.
        return components.browse() if claim.source_task_id else components

    def _sync_part_materials(self):
        result = super()._sync_part_materials()
        for order in self.filtered(lambda item: item.state == "new"):
            claim = order._get_linked_sale_order().maintenance_claim_id
            if not claim.source_task_id:
                continue
            tasks = order.service_ids.filtered(lambda task: task.product_id == claim.service_product_id)
            if len(tasks) != 1:
                continue
            # Appointment preparation can supply today's complete BOM before
            # the work order exists. Replace only those unissued repair rows.
            order.product_ids.filtered(
                lambda row: row.service_id == claim.service_product_id
                and not row.maintenance_origin_material_id and not row.material_move_id
            ).sudo().unlink()
            existing = order.product_ids.maintenance_origin_material_id
            for part in claim.part_ids.filtered("include"):
                if part.source_material_id in existing:
                    continue
                self.env["car.workorder.product"].sudo().with_context(maintenance_source_token=_SOURCE_TOKEN).create({
                    "workorder_id": order.id, "service_id": claim.service_product_id.id,
                    "source_task_id": tasks.id, "part_id": part.vehicle_part_id.id,
                    "maintenance_origin_material_id": part.source_material_id.id,
                    "product_id": part.product_id.id, "quantity": part.quantity,
                    "suggested_qty": part.quantity, "used_uom_id": part.product_id.uom_id.id,
                    "material_category_id": part.source_material_id.material_category_id.id,
                    "usage_mode": part.source_material_id.usage_mode,
                    "standard_length_in": part.source_material_id.standard_length_in,
                    "standard_width_in": part.source_material_id.standard_width_in,
                    "actual_length_in": part.source_material_id.actual_length_in,
                    "actual_width_in": part.source_material_id.actual_width_in,
                    "allowed_brand_ids": [(6, 0, part.source_material_id.allowed_brand_ids.ids)],
                    "material_brand_id": part.source_material_id.material_brand_id.id,
                })
        return result


class WorkOrderMaterial(models.Model):
    _inherit = "car.workorder.product"

    maintenance_origin_material_id = fields.Many2one("car.workorder.product", readonly=True, copy=False, ondelete="restrict")

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get("maintenance_origin_material_id") for vals in vals_list) and self.env.context.get("maintenance_source_token") is not _SOURCE_TOKEN:
            raise UserError(_("The original repair material is managed by the maintenance request."))
        return super().create(vals_list)

    def write(self, vals):
        if "maintenance_origin_material_id" in vals:
            raise UserError(_("The original repair material cannot be changed."))
        return super().write(vals)


class VehiclePart(models.Model):
    _inherit = "car.part"

    maintenance_glass_type_id = fields.Many2one("window.tint.glass.type", string="Tint Glass Type", ondelete="restrict")


class WorkOrderService(models.Model):
    _inherit = "car.workorder.service"

    @api.depends("product_id", "workorder_id.name")
    def _compute_display_name(self):
        for task in self:
            task.display_name = "%s / %s" % (task.workorder_id.name or "", task.product_id.display_name or "")
