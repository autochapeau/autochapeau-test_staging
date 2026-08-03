from odoo import api, models
from odoo.osv import expression


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _vehicle_size_domain(self, size):
        """Products without a Size attribute, or variants matching the car size."""
        if not size:
            return []
        templates = self.env["product.template"]
        size_attributes = templates._vehicle_size_attributes()
        if not size_attributes:
            return []
        sized_templates = templates.with_context(
            skip_vehicle_size_filter=True, active_test=False
        ).search([
            ("attribute_line_ids.attribute_id", "in", size_attributes.ids),
        ])
        return expression.OR([
            [("product_tmpl_id", "not in", sized_templates.ids)],
            [(
                "product_template_variant_value_ids.product_attribute_value_id.code",
                "=",
                size,
            )],
        ])

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        size = self.env.context.get("vehicle_size_filter")
        if size and not self.env.context.get("skip_vehicle_size_filter"):
            size_domain = self._vehicle_size_domain(size)
            if size_domain:
                domain = expression.AND([domain, size_domain])
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            access_rights_uid=access_rights_uid,
        )
