from . import models


def post_init_hook(env):
    env["product.product"].search([("detailed_type", "=", "service")])._sync_service_tag()
    env.cr.execute(
        """
        UPDATE car_workorder_product AS line
           SET suggested_qty = bom.quantity
          FROM car_bom AS bom
         WHERE line.service_id = bom.service_id
           AND line.product_id = bom.product_id
           AND COALESCE(line.suggested_qty, 0) = 0
           AND bom.quantity <> 0
        """
    )
