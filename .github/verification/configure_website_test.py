"""Initialize TEST counters from existing public totals; add a labelled QA offer."""
import json
from odoo import fields

assert env.cr.dbname == "autochapeau_prod_test"
counters = env["portal.statistic"].sudo().with_context(lang="en_US")
starting = fields.Datetime.now()
for name, metric, legacy in (("Number of cars", "cars", "19"), ("Number of clients", "customers", "13")):
    counter = counters.search([("name", "=", name)], limit=1)
    # The existing public UI displays these legacy values with a K suffix.
    # Never overwrite a counter that an administrator has already configured.
    if counter and counter.metric == "manual" and counter.value == legacy:
        counter.write({"metric": metric, "opening_value": int(legacy) * 1000,
                       "count_from": starting, "car_count_mode": "unique"})
if not counters.search_count([("metric", "=", "services")]):
    completed = env["car.workorder.service"].sudo().search_count([
        ("state", "=", "done"), ("date_end", "<", starting),
        ("workorder_id.state", "!=", "cancelled")])
    counter = counters.create({"name": "Completed services", "value": str(completed),
        "metric": "services", "opening_value": completed, "count_from": starting})
    counter.with_context(lang="ar_001").name = "الخدمات المكتملة"
product = env["product.product"].sudo().with_context(lang="en_US").search([
    ("name", "=", "Shampoo Car Wash"), ("is_published", "=", True),
    ("sale_ok", "=", True), ("detailed_type", "!=", "service")], limit=1)
offer = env["portal.offer"].sudo().with_context(active_test=False).search([
    ("name", "=", "DEMO Website QA Offer")], limit=1)
if product and not offer:
    offer = env["portal.offer"].sudo().create({"name": "DEMO Website QA Offer",
        "summary": "Fictional TEST offer for purchase-link verification",
        "details": "<p>TEST ONLY customer acceptance fixture</p>", "product_id": product.id,
        "is_main": False})
env.cr.commit()
print("TEST_WEBSITE_CONFIGURATION=" + json.dumps({
    "counters": [{"id": row.id, "metric": row.metric, "opening_value": row.opening_value,
                   "count_from": str(row.count_from), "value": row._website_value()} for row in counters.search([])],
    "qa_offer_id": offer.id if offer else False,
    "google_sources": env["portal.google.review.source"].sudo().search_count([]),
    "unlinked_existing_offers": env["portal.offer"].sudo().search_count([("product_id", "=", False)]),
}, sort_keys=True))
