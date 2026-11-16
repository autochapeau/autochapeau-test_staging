"""Create isolated fictional TEST data for the customer maintenance UI."""
import json
import secrets

from odoo import Command

assert env.cr.dbname == "autochapeau_prod_test"
qa = env(context=dict(env.context, tracking_disable=True, mail_create_nosubscribe=True,
                      mail_notrack=True, no_reset_password=True))
login = "website-qa@example.invalid"
password = secrets.token_urlsafe(32)
user = qa["res.users"].with_context(active_test=False).search([("login", "=", login)], limit=1)
if not user:
    user = qa["res.users"].create({"name": "DEMO Website QA Customer", "login": login,
        "email": login, "password": password, "groups_id": [Command.set(qa.ref("base.group_portal").ids)]})
else:
    assert user.has_group("base.group_portal") and not user.has_group("base.group_user")
    assert user.partner_id.name == "DEMO Website QA Customer"
    user.write({"password": password, "active": True})
reference = "DEMO Website QA Maintenance 20261116"
sale = qa["sale.order"].search([("client_order_ref", "=", reference)], limit=1)
if not sale:
    original = qa["sale.order"].search([("client_order_ref", "=", "DEMO Maintenance Actual Parts 20261116")], limit=1)
    assert original and original.partner_id.name == "DEMO Guide Customer"
    source = qa["car.work.order"].search([("sale_order_id", "=", original.id)], limit=1)
    assert source and source.product_ids
    vehicle = qa["fleet.vehicle"].create({"model_id": original.vehicle_id.model_id.id,
        "partner_id": user.partner_id.id, "vin_sn": "DEMOWEBSITE261116"})
    sale = qa["sale.order"].create({"partner_id": user.partner_id.id,
        "vehicle_id": vehicle.id, "order_type": "intern", "branch_id": original.branch_id.id,
        "warehouse_id": original.warehouse_id.id, "company_id": original.company_id.id,
        "client_order_ref": reference, "order_line": [Command.create({
            "product_id": original.order_line.product_id.id, "price_unit": 500})]})
    sale.state = "sale"
    order = qa["car.work.order"].with_context(contract_upsell_sync=True).create({
        "partner_id": user.partner_id.id, "vehicle_id": vehicle.id, "sale_order_id": sale.id,
        "company_id": original.company_id.id, "branch_id": original.branch_id.id,
        "notes": "Fictional website acceptance fixture only",
        "service_ids": [Command.create({"product_id": original.order_line.product_id.id,
            "staff_ids": [Command.set(source.service_ids.staff_ids.ids)]})]})
    order.picking_id = order._create_delivery_picking()
    order.state = "confirmed"
    order.action_start_materials()
    order.action_finish_materials()
assert sale.partner_id == user.partner_id
qa.cr.commit()
# The workflow captures stdout privately and encrypts this on the runner.
# Never print this payload directly to a public job log.
print("WEBSITE_QA_RESULT=" + json.dumps({"login": login, "password": password,
    "order_id": sale.id, "order_name": sale.name, "user_id": user.id}))
