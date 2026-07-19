from odoo import fields, models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    def action_apply_pricelist_discount(self):
        """Apply the pricelist discount price to products using today's date without time."""
        self.ensure_one()
        # Only get products available for sale
        products = self.env["product.product"].search([("sale_ok", "=", True)])
        for product in products:
            # Applicable pricelist rule for the product
            pricelist_items = (
                self.env["product.pricelist.item"]
                .sudo()
                .search(
                    [
                        ("pricelist_id", "=", self.id),
                        ("pricelist_id.discount_policy", "=", "with_discount"),
                        "|",
                        ("pricelist_id.company_id", "=", False),
                        ("pricelist_id.company_id", "=", self.env.company.id),
                        "|",
                        "|",
                        "&",
                        ("applied_on", "=", "0_product_variant"),
                        ("product_id", "=", product.id),
                        "&",
                        ("applied_on", "=", "2_product_category"),
                        ("categ_id", "child_of", product.categ_id.id),
                        ("applied_on", "=", "3_global"),
                    ],
                    order="applied_on asc, min_quantity desc",
                )
            )
            if pricelist_items:
                rule = pricelist_items[0]
                currency = rule.currency_id or product.currency_id
                price = rule._compute_price(
                    product=product,
                    quantity=1.0,
                    uom=product.uom_id,
                    date=fields.Date.context_today(self),
                    currency=currency,
                )
                product.lst_price_discount = price
            else:
                product.lst_price_discount = 0.0
