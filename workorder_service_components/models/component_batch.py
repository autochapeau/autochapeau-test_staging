from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ServiceComponentBatch(models.TransientModel):
    _name = "car.service.component.batch"
    _description = "Configure Materials for Multiple Service Variants"

    product_tmpl_id = fields.Many2one("product.template", required=True, ondelete="cascade")
    service_ids = fields.Many2many("product.product", string="Service Variants", required=True)
    part_id = fields.Many2one("car.part", string="Vehicle Part")
    part_ids = fields.Many2many("car.part", string="Vehicle Parts")
    variant_line_ids = fields.One2many("car.service.component.batch.variant", "batch_id", string="Size Overrides")
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
        if len(self.variant_line_ids.service_id) != len(self.variant_line_ids):
            raise ValidationError(_("Enter only one size override per variant."))
        if self.variant_line_ids.service_id - self.service_ids:
            raise ValidationError(_("Size overrides must belong to the selected variants."))
        for service in self.service_ids:
            override = self.variant_line_ids.filtered(lambda row: row.service_id == service)
            for part_id in (self.part_ids | self.part_id).ids or [False]:
                part = Part.search([("service_id", "=", service.id), ("part_id", "=", part_id)], limit=1)
                if not part:
                    part = Part.create({"service_id": service.id, "part_id": part_id})
                for line in self.line_ids:
                    existing = part.component_ids.filtered(lambda bom: bom.product_id == line.product_id and
                        (bool(line.product_id) or bom.material_category_id == line.material_category_id))
                    if len(existing) > 1:
                        raise ValidationError(_("This part has duplicate materials. Review its existing configuration first."))
                    vals = {
                        "material_category_id": line.material_category_id.id,
                        "quantity": override.quantity if override else line.quantity,
                        "product_uom_id": (override.product_uom_id or line.product_uom_id).id,
                        "usage_mode": line.usage_mode,
                        "standard_length_in": override.standard_length_in if override else line.standard_length_in,
                        "standard_width_in": override.standard_width_in if override else line.standard_width_in,
                        "allowed_brand_ids": [fields.Command.set(line.allowed_brand_ids.ids)],
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
    product_id = fields.Many2one("product.product", string="Product")
    quantity = fields.Float(digits=(16, 4), string="Default Quantity", default=1, required=True)
    product_uom_category_id = fields.Many2one(related="product_id.uom_id.category_id")
    product_uom_id = fields.Many2one("uom.uom", string="UoM")

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
            if line.product_id and not self.env["product.product"].search_count([
                ("id", "=", line.product_id.id), ("detailed_type", "=", "product"),
                ("categ_id", "child_of", line.material_category_id.id),
            ]):
                raise ValidationError(_("Select a storable material from the selected category or its subcategories."))
            if line.usage_mode != "roll" and (line.quantity <= 0 or not line.product_uom_id):
                raise ValidationError(_("Enter a positive quantity and a unit of measure."))
            if line.product_id and line.product_uom_id and line.product_uom_id.category_id != line.product_id.uom_id.category_id:
                raise ValidationError(_("Enter a positive quantity and a compatible unit of measure."))


class ServiceComponentBatchVariant(models.TransientModel):
    _name = "car.service.component.batch.variant"
    _description = "Service Size Material Override"

    batch_id = fields.Many2one("car.service.component.batch", required=True, ondelete="cascade")
    service_id = fields.Many2one("product.product", string="Service Variant", required=True)
    quantity = fields.Float(digits=(16, 4), string="Default Quantity", default=1)
    product_uom_id = fields.Many2one("uom.uom", string="UoM")
    standard_length_in = fields.Float(string="Standard Length (in)", digits=(16, 4))
    standard_width_in = fields.Float(string="Standard Width (in)", digits=(16, 4))

    @api.constrains("quantity", "standard_length_in", "standard_width_in")
    def _check_positive(self):
        for row in self:
            if min(row.quantity, row.standard_length_in, row.standard_width_in) < 0:
                raise ValidationError(_("Quantities and dimensions cannot be negative."))
