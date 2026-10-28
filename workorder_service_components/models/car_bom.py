from odoo import api, fields, models


class CarBom(models.Model):
    _inherit = "car.bom"

    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Service Template",
        ondelete="cascade",
        index=True,
        copy=False,
    )
    product_uom_category_id = fields.Many2one(
        related="product_id.uom_id.category_id",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        domain="[('category_id', '=', product_uom_category_id)]",
    )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        self.product_uom_id = self.product_id.uom_id if self.product_id else False

    @api.model_create_multi
    def create(self, vals_list):
        self._complete_component_vals(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("service_id") and "product_tmpl_id" not in vals:
            service = self.env["product.product"].browse(vals["service_id"])
            vals = dict(vals, product_tmpl_id=service.product_tmpl_id.id)
        return super().write(vals)

    @api.model
    def _complete_component_vals(self, vals_list):
        Product = self.env["product.product"]
        Template = self.env["product.template"]
        for vals in vals_list:
            if vals.get("product_id") and not vals.get("product_uom_id"):
                product = Product.browse(vals["product_id"])
                if product.uom_id:
                    vals["product_uom_id"] = product.uom_id.id
            if vals.get("service_id") and not vals.get("product_tmpl_id"):
                service = Product.browse(vals["service_id"])
                vals["product_tmpl_id"] = service.product_tmpl_id.id
            elif vals.get("product_tmpl_id") and not vals.get("service_id"):
                template = Template.browse(vals["product_tmpl_id"])
                variant = template.product_variant_id or template.product_variant_ids[:1]
                if variant:
                    vals["service_id"] = variant.id

    def _auto_init(self):
        result = super()._auto_init()
        self.env.cr.execute(
            """
            UPDATE car_bom AS bom
               SET product_uom_id = template.uom_id
              FROM product_product AS product
              JOIN product_template AS template
                ON template.id = product.product_tmpl_id
             WHERE bom.product_id = product.id
               AND bom.product_uom_id IS NULL
            """
        )
        self.env.cr.execute(
            """
            UPDATE car_bom AS bom
               SET product_tmpl_id = product.product_tmpl_id
              FROM product_product AS product
             WHERE bom.service_id = product.id
               AND bom.product_tmpl_id IS NULL
            """
        )
        return result
