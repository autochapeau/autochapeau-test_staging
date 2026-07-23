from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    restrict_pricelist_products = fields.Boolean(
        compute="_compute_pricelist_product_domain",
    )

    allowed_pricelist_template_ids = fields.Many2many(
        comodel_name="product.template",
        compute="_compute_pricelist_product_domain",
        string="Allowed Pricelist Products",
    )

    @api.depends(
        "order_id.pricelist_id",
        "order_id.pricelist_id.item_ids",
        "order_id.pricelist_id.item_ids.applied_on",
        "order_id.pricelist_id.item_ids.product_id",
        "order_id.pricelist_id.item_ids.product_tmpl_id",
        "order_id.pricelist_id.item_ids.categ_id",
    )
    def _compute_pricelist_product_domain(self):
        ProductTemplate = self.env["product.template"]

        for line in self:
            line.restrict_pricelist_products = False
            line.allowed_pricelist_template_ids = False

            pricelist = line.order_id.pricelist_id

            # لا توجد Pricelist:
            # لا نطبّق restriction وتظهر المنتجات العادية
            if not pricelist:
                continue

            items = pricelist.item_ids

            # Pricelist فارغة:
            # لا نطبّق restriction وتظهر المنتجات العادية
            if not items:
                continue

            # وجود Global Rule يعني أن القائمة تطبق على جميع المنتجات
            if any(item.applied_on == "3_global" for item in items):
                continue

            template_ids = set()
            category_ids = set()

            for item in items:
                # Product Template
                if (
                    item.applied_on == "1_product"
                    and item.product_tmpl_id
                ):
                    template_ids.add(item.product_tmpl_id.id)

                # Product Variant
                elif (
                    item.applied_on == "0_product_variant"
                    and item.product_id
                ):
                    template_ids.add(item.product_id.product_tmpl_id.id)

                # Product Category
                elif (
                    item.applied_on == "2_product_category"
                    and item.categ_id
                ):
                    category_ids.add(item.categ_id.id)

            domain = [
                ("sale_ok", "=", True),
                ("active", "=", True),
            ]

            product_domain = []

            if template_ids:
                product_domain.append(("id", "in", list(template_ids)))

            if category_ids:
                category_domain = [
                    ("categ_id", "child_of", list(category_ids)),
                ]

                category_templates = ProductTemplate.search(
                    domain + category_domain
                )

                template_ids.update(category_templates.ids)

            # search بدون sudo حتى تُطبّق Product multi-company rules
            accessible_templates = ProductTemplate.search([
                ("id", "in", list(template_ids)),
                ("sale_ok", "=", True),
                ("active", "=", True),
            ])

            line.restrict_pricelist_products = True
            line.allowed_pricelist_template_ids = accessible_templates