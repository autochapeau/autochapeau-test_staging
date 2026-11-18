import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    website_card_price_enabled = fields.Boolean(
        string="Custom Website Card Price",
        help="Show a manually selected starting price on the service card. "
             "This does not change variant prices, cart totals or payment amounts.",
    )
    website_card_price = fields.Monetary(
        string="Website Card Starting Price", currency_field="currency_id",
    )
    website_card_price_label = fields.Char(
        string="Website Card Price Label", translate=True,
        help="For example: Starts from. Leave empty to use the website's translated label.",
    )

    @api.constrains("website_card_price_enabled", "website_card_price")
    def _check_website_card_price(self):
        for template in self:
            if template.website_card_price_enabled and (
                not math.isfinite(template.website_card_price) or template.website_card_price < 0
            ):
                raise ValidationError(_("The website card starting price must be a non-negative number."))

    def _website_card_price_payload(self):
        self.ensure_one()
        return {
            "website_card_price": self.website_card_price if self.website_card_price_enabled else None,
            "website_card_price_label": self.website_card_price_label or False,
        }
