from odoo import api, models
from odoo.osv import expression


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _vehicle_size_attributes(self):
        """The Size attribute, matched the same way as cars_management does."""
        attributes = self.env["product.attribute"].with_context(lang="en_US").search([])
        return attributes.filtered(
            lambda attribute: (attribute.name or "").strip().lower() == "size"
        )

    @api.model
    def _vehicle_size_domain(self, size):
        """Templates without a Size attribute, or offering the car size."""
        if not size:
            return []
        size_attributes = self._vehicle_size_attributes()
        if not size_attributes:
            return []
        templates = self.with_context(
            skip_vehicle_size_filter=True, active_test=False
        )
        sized = templates.search([
            ("attribute_line_ids.attribute_id", "in", size_attributes.ids),
        ])
        matching = templates.search([
            ("attribute_line_ids.attribute_id", "in", size_attributes.ids),
            ("attribute_line_ids.value_ids.code", "=", size),
        ])
        return expression.OR([
            [("id", "not in", sized.ids)],
            [("id", "in", matching.ids)],
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

    @api.model
    def get_vehicle_size_ptav_ids(self, product_tmpl_ids, size):
        """Return the Size values allowed for a car size, per template.

        Called by the product configurator to keep only the car size selectable.
        JSON turns the keys into strings.

        :return: {
            tmpl_id: {
                ptal_id: {
                    "allowed_ids": [matching_ptav_id],
                    "all_ids": [all_size_ptav_ids],
                },
            },
        }
        """
        result = {}
        if not size or not product_tmpl_ids:
            return result
        size_attributes = self._vehicle_size_attributes()
        if not size_attributes:
            return result
        for template in self.browse(product_tmpl_ids).exists():
            lines = {}
            for ptal in template.attribute_line_ids:
                if ptal.attribute_id not in size_attributes:
                    continue
                ptavs = ptal.product_template_value_ids.filtered(
                    lambda ptav: ptav.product_attribute_value_id.code == size
                )
                if ptavs:
                    lines[str(ptal.id)] = {
                        "allowed_ids": ptavs.ids,
                        "all_ids": ptal.product_template_value_ids.ids,
                    }
            if lines:
                result[str(template.id)] = lines
        return result
