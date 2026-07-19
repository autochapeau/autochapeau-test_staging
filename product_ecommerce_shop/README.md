# Product Ecommerce Shop

A small module that adds an "Ecommerce Shop" section (checkbox `Is Published`) in the "Sales" tab of the product variant card.

## Installation

1. Copy the `product_ecommerce_shop` folder into the `custom_addons` directory.
2. Update the module list and install `Product Ecommerce Shop` from the Apps interface, or:

```bash
cd /opt/odoo/odoo
./odoo-bin -d <your_db> --addons-path="/opt/odoo/odoo/addons,/opt/odoo/odoo/custom_addons/autochapeau-17.0" -i product_ecommerce_shop
```

## Notes

-   The module only adds the `is_published` field and the view. If you want to automatically publish the product on a website, you will need to add the integration logic with `website`/`website_sale`.
