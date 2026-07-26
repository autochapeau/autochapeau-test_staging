from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        fields_list = result["search_params"]["fields"]
        if "product_template_variant_value_ids" not in fields_list:
            fields_list.append("product_template_variant_value_ids")
        return result

    def _process_pos_ui_product_product(self, products):
        super()._process_pos_ui_product_product(products)
        if not products:
            return

        product_ids = [p["id"] for p in products]
        products_rs = self.env["product.product"].browse(product_ids)
        size_data = {}
        for product in products_rs:
            has_size = False
            size_codes = []
            for ptav in product.product_template_variant_value_ids:
                attr_name = (
                    ptav.attribute_id.with_context(lang="en_US").name or ""
                ).strip().lower()
                if attr_name == "size":
                    has_size = True
                    code = ptav.product_attribute_value_id.code
                    if code:
                        size_codes.append(code)
            size_data[product.id] = {
                "has_size_attribute": has_size,
                "size_attribute_codes": size_codes,
            }

        for product in products:
            info = size_data.get(product["id"], {})
            product["has_size_attribute"] = info.get("has_size_attribute", False)
            product["size_attribute_codes"] = info.get("size_attribute_codes", [])
