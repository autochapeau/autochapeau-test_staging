from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ServiceComponentBatch(models.TransientModel):
    _name = "car.service.component.batch"
    _description = "Configure Materials for Multiple Service Variants"

    product_tmpl_id = fields.Many2one("product.template", required=True, ondelete="cascade")
    service_ids = fields.Many2many("product.product", string="Service Variants", required=True)
    part_id = fields.Many2one("car.part", string="Vehicle Part", required=True)
    line_ids = fields.One2many("car.service.component.batch.line", "batch_id", string="Materials", required=True)

    def action_apply(self):
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group("work_orders.group_workshop_manager"):
            raise AccessError(_("Only workshop managers can configure service materials."))
        if self.product_tmpl_id.detailed_type != "service" or not self.service_ids or not self.line_ids:
            raise ValidationError(_("Select a service, at least one variant and at least one material."))
        if any(service.product_tmpl_id != self.product_tmpl_id for service in self.service_ids):
            raise ValidationError(_("All variants must belong to the selected service template."))
        # Serialize configuration of the same variants, including repeated Apply.
        self.env.cr.execute("SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE", (tuple(self.service_ids.ids),))
        self.line_ids._check_material()
        keys = [(line.material_category_id.id, line.product_id.id) for line in self.line_ids]
        if len(keys) != len(set(keys)):
            raise ValidationError(_("Do not add the same material and category more than once."))
        Part = self.env["car.service.part"]
        Bom = self.env["car.bom"]
        for service in self.service_ids:
            part = Part.search([("service_id", "=", service.id), ("part_id", "=", self.part_id.id)], limit=1)
            if not part:
                part = Part.create({"service_id": service.id, "part_id": self.part_id.id})
            for line in self.line_ids:
                existing = part.component_ids.filtered(lambda bom: bom.product_id == line.product_id)
                if len(existing) > 1:
                    raise ValidationError(_("This part has duplicate materials. Review its existing configuration first."))
                vals = {
                    "material_category_id": line.material_category_id.id,
                    "quantity": line.quantity, "product_uom_id": line.product_uom_id.id,
                }
                if existing:
                    existing.write(vals)
                else:
                    Bom.create(dict(vals, service_part_id=part.id, product_id=line.product_id.id))
        return {"type": "ir.actions.act_window_close"}


class ServiceComponentBatchLine(models.TransientModel):
    _name = "car.service.component.batch.line"
    _description = "Batch Service Material"

    batch_id = fields.Many2one("car.service.component.batch", required=True, ondelete="cascade")
    material_category_id = fields.Many2one(
        "product.category", string="Material Category", required=True,
        domain="[('is_main_material_category', '=', True)]",
    )
    product_id = fields.Many2one("product.product", string="Product", required=True)
    quantity = fields.Float(string="Default Quantity", default=1, required=True)
    product_uom_category_id = fields.Many2one(related="product_id.uom_id.category_id")
    product_uom_id = fields.Many2one("uom.uom", string="UoM", required=True)

    @api.onchange("product_id")
    def _onchange_product(self):
        self.product_uom_id = self.product_id.uom_id

    @api.onchange("material_category_id")
    def _onchange_category(self):
        self.product_id = False
        self.product_uom_id = False

    @api.constrains("material_category_id", "product_id", "quantity", "product_uom_id")
    def _check_material(self):
        for line in self:
            if not line.material_category_id.is_main_material_category:
                raise ValidationError(_("Select a main material category."))
            if not self.env["product.product"].search_count([
                ("id", "=", line.product_id.id), ("detailed_type", "=", "product"),
                ("categ_id", "child_of", line.material_category_id.id),
            ]):
                raise ValidationError(_("Select a storable material from the selected category or its subcategories."))
            if line.quantity <= 0 or line.product_uom_id.category_id != line.product_id.uom_id.category_id:
                raise ValidationError(_("Enter a positive quantity and a compatible unit of measure."))
