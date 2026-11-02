from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CarPart(models.Model):
    _name = "car.part"
    _description = "Vehicle Part"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class ServicePart(models.Model):
    _name = "car.service.part"
    _description = "Service Vehicle Part and Materials"
    _rec_name = "part_id"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    part_id = fields.Many2one("car.part", required=True, ondelete="restrict")
    service_id = fields.Many2one(
        "product.product", string="Service", required=True, ondelete="cascade",
        domain="[('detailed_type', '=', 'service')]", index=True,
    )
    product_tmpl_id = fields.Many2one(
        related="service_id.product_tmpl_id", store=True, index=True,
    )
    component_ids = fields.One2many("car.bom", "service_part_id", string="Materials", copy=True)
    component_count = fields.Integer(compute="_compute_component_count")

    _sql_constraints = [
        ("service_part_unique", "unique(service_id, part_id)",
         "This vehicle part is already configured for this service."),
    ]

    @api.depends("component_ids")
    def _compute_component_count(self):
        for record in self:
            record.component_count = len(record.component_ids)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        template_id = self.env.context.get("default_product_tmpl_id")
        if "service_id" in fields_list and not values.get("service_id") and template_id:
            template = self.env["product.template"].browse(template_id)
            if template.product_variant_count == 1:
                values["service_id"] = template.product_variant_id.id
        return values

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("service_id") and vals.get("product_tmpl_id"):
                template = self.env["product.template"].browse(vals["product_tmpl_id"])
                if template.product_variant_count == 1:
                    vals["service_id"] = template.product_variant_id.id
        return super().create(vals_list)

    @api.constrains("service_id")
    def _check_service(self):
        for record in self:
            if record.service_id.detailed_type != "service":
                raise ValidationError(_("Vehicle parts can only be configured on services."))

    def write(self, vals):
        result = super().write(vals)
        if "service_id" in vals:
            for record in self:
                record.component_ids.write({"service_id": record.service_id.id})
        return result


class ProductProduct(models.Model):
    _inherit = "product.product"

    service_part_ids = fields.One2many("car.service.part", "service_id", string="Vehicle Parts", copy=True)
    ungrouped_component_ids = fields.One2many(
        "car.bom", "service_id", domain=[("service_part_id", "=", False)],
        string="Existing Ungrouped Materials",
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    service_part_ids = fields.One2many("car.service.part", "product_tmpl_id", string="Vehicle Parts")
    ungrouped_component_ids = fields.One2many(
        "car.bom", "product_tmpl_id", domain=[("service_part_id", "=", False)],
        string="Existing Ungrouped Materials",
    )


class CarBom(models.Model):
    _inherit = "car.bom"

    service_part_id = fields.Many2one(
        "car.service.part", string="Service Part", ondelete="cascade", index=True,
    )
    part_id = fields.Many2one(related="service_part_id.part_id", store=True, string="Vehicle Part")
    product_id = fields.Many2one(domain="[('detailed_type', '=', 'product')]")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("service_part_id"):
                part = self.env["car.service.part"].browse(vals["service_part_id"])
                vals.update(service_id=part.service_id.id, product_tmpl_id=part.product_tmpl_id.id)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("service_part_id"):
            part = self.env["car.service.part"].browse(vals["service_part_id"])
            vals = dict(vals, service_id=part.service_id.id, product_tmpl_id=part.product_tmpl_id.id)
        if vals.get("product_id") and "product_uom_id" not in vals:
            vals = dict(vals, product_uom_id=self.env["product.product"].browse(vals["product_id"]).uom_id.id)
        return super().write(vals)

    @api.constrains("service_part_id", "service_id", "product_id", "quantity", "product_uom_id")
    def _check_part_material(self):
        for line in self.filtered("service_part_id"):
            if line.service_id != line.service_part_id.service_id:
                raise ValidationError(_("The material must belong to the vehicle part's service."))
            if line.product_id.detailed_type != "product":
                raise ValidationError(_("Service materials must be storable products."))
            if line.quantity <= 0:
                raise ValidationError(_("The default material quantity must be greater than zero."))
            if not line.product_uom_id or line.product_uom_id.category_id != line.product_id.uom_id.category_id:
                raise ValidationError(_("The material unit must match the product's unit category."))
