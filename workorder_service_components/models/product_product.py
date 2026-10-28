from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    service_component_ids = fields.One2many(
        "car.bom",
        "product_tmpl_id",
        string="Service Components",
    )
    service_tag_id = fields.Many2one(
        related="product_variant_id.service_tag_id",
        string="Service Tag",
    )

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._assign_component_variants()
        templates.product_variant_ids._sync_service_tag()
        return templates

    def write(self, vals):
        result = super().write(vals)
        if {"name", "detailed_type", "type"} & set(vals):
            self._assign_component_variants()
            self.product_variant_ids._sync_service_tag()
        return result

    def _assign_component_variants(self):
        """Attach template components to the single variant once it exists."""
        for template in self.filtered(lambda item: item.detailed_type == "service"):
            variant = template.product_variant_id
            if not variant:
                continue
            lines = template.service_component_ids.filtered(lambda line: not line.service_id)
            if lines:
                lines.write({"service_id": variant.id})


class ProductProduct(models.Model):
    _inherit = "product.product"

    service_tag_id = fields.Many2one(
        "product.tag",
        string="Service Tag",
        copy=False,
        help="A tag with the same name is created automatically. "
             "It only filters products on the work order; products are not assigned to it automatically.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        products._sync_service_tag()
        return products

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("skip_service_tag_sync") and {"name", "detailed_type", "type"} & set(vals):
            self._sync_service_tag()
        return result

    def _sync_service_tag(self):
        """Create or reuse one tag named like the service, without linking products."""
        Tag = self.env["product.tag"].sudo()
        for product in self:
            name = (product.name or "").strip()
            if product.detailed_type != "service" or not name:
                continue
            current = product.service_tag_id
            if current and current.sudo().name == name:
                continue
            existing = Tag.search([("name", "=", name)], limit=1)
            if existing:
                if current != existing:
                    product.with_context(skip_service_tag_sync=True).write({
                        "service_tag_id": existing.id,
                    })
                continue
            shared = bool(current) and bool(self.sudo().search_count([
                ("service_tag_id", "=", current.id),
                ("id", "!=", product.id),
            ]))
            if current and not shared:
                current.sudo().name = name
                continue
            tag = Tag.create({"name": name})
            product.with_context(skip_service_tag_sync=True).write({
                "service_tag_id": tag.id,
            })
