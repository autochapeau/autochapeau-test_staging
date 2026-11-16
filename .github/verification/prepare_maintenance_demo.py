"""Idempotent, fictional training fixture for the authorized TEST tutorial."""
import json
assert env.cr.dbname == "autochapeau_prod_test", "Training fixtures are TEST-only"
reference = "DEMO Maintenance Actual Parts 20261116"
Sale = env["sale.order"].sudo().with_context(tracking_disable=True, mail_create_nosubscribe=True)
sale = Sale.search([("client_order_ref", "=", reference)], limit=1)
if not sale:
    customer = env["res.partner"].search([("name", "=", "DEMO Guide Customer")], limit=1)
    vehicle = env["fleet.vehicle"].search([("vin_sn", "=", "DEMOMAINT261116")], limit=1)
    branch = env["hr.department"].search([("name", "=", "DEMO Guide Branch")], limit=1)
    staff = env["hr.employee"].search([("name", "=", "DEMO Guide Technician"), ("branch_id", "=", branch.id)], limit=1)
    warehouse = env["stock.warehouse"].search([("branch_id", "=", branch.id)], limit=1)
    assert customer and vehicle and branch and staff and warehouse
    assert not customer.phone and not customer.mobile and not customer.email
    company = warehouse.company_id
    env = env(context=dict(env.context, allowed_company_ids=[company.id], tracking_disable=True, mail_create_nosubscribe=True))
    unit = env.ref("uom.product_uom_unit")
    service = env["product.product"].create({"name": "DEMO Maintenance Service (Small)", "detailed_type": "service", "list_price": 500})
    materials = []
    for name, cost in (("DEMO Maintenance Film", 30), ("DEMO Maintenance Liquid", 40)):
        product = env["product.product"].with_company(company).create({"name": name, "detailed_type": "product", "uom_id": unit.id, "uom_po_id": unit.id, "standard_price": cost})
        env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 50)
        materials.append(product)
    parts = []
    for label, product, quantity in (("DEMO Maintenance Right Door", materials[0], 4),
                                     ("DEMO Maintenance Left Door", materials[1], 2),
                                     ("DEMO Maintenance Rear Door", materials[0], 1)):
        part = env["car.part"].create({"name": label})
        env["car.service.part"].create({"service_id": service.id, "part_id": part.id,
            "component_ids": [(0, 0, {"product_id": product.id, "quantity": 1})]})
        parts.append((part, quantity))
    sale = Sale.with_company(company).create({"partner_id": customer.id, "vehicle_id": vehicle.id,
        "order_type": "intern", "branch_id": branch.id, "warehouse_id": warehouse.id,
        "company_id": company.id, "client_order_ref": reference,
        "order_line": [(0, 0, {"product_id": service.id, "product_uom_qty": 1, "price_unit": 500})]})
    sale.action_confirm()
    workorder = env["car.work.order"].with_context(contract_upsell_sync=True).create({"partner_id": customer.id, "vehicle_id": vehicle.id,
        "sale_order_id": sale.id, "branch_id": branch.id, "company_id": company.id,
        "service_ids": [(0, 0, {"product_id": service.id, "staff_ids": [(6, 0, staff.ids)]})]})
    for part, quantity in parts:
        workorder.product_ids.filtered(lambda row: row.part_id == part).quantity = quantity
    workorder.picking_id = workorder._create_delivery_picking()
    workorder.state = "confirmed"
    workorder.action_start_materials()
    workorder.action_finish_materials()
    env.cr.commit()
else:
    workorder = env["car.work.order"].search([("sale_order_id", "=", sale.id)], limit=1)
print("MAINTENANCE_TRAINING_FIXTURE=" + json.dumps({"sale_id": sale.id, "sale_name": sale.name,
    "workorder_id": workorder.id, "workorder_name": workorder.name, "service_id": sale.order_line.product_id.id,
    "parts": workorder.product_ids.part_id.ids, "actual_material_rows": workorder.product_ids.ids}))
