"""Seed only the existing fictional TEST service and audit release prerequisites."""
import json

assert env.cr.dbname == "autochapeau_prod_test"
qa = env(context=dict(env.context, tracking_disable=True, mail_create_nosubscribe=True))
template = qa["product.template"].browse(4495).exists()
assert template and template.name.startswith("DEMO Website QA Media Service"), "Expected the isolated QA media service"
prices_before = {v.id: v.lst_price for v in template.product_variant_ids}
template.with_context(lang="en_US").write({
    "website_card_price_enabled": True, "website_card_price": 13800,
    "website_card_price_label": "Starts from",
})
template.with_context(lang="ar_001").website_card_price_label = "يبدأ من"
template.product_variant_ids.write({"expected_duration": 14, "warranty": 10})
assert prices_before == {v.id: v.lst_price for v in template.product_variant_ids}
assert template.with_context(lang="en_US")._website_card_price_payload()["website_card_price_label"] == "Starts from"
assert template.with_context(lang="ar_001")._website_card_price_payload()["website_card_price_label"] == "يبدأ من"
# Make the brand-image acceptance observable, using only the fictional QA brand.
brand = qa["fleet.vehicle.model.brand"].search([("name", "=", "DEMO Guide Car")], limit=1)
if brand and not brand.image_128:
    brand.image_128 = template.image_128
env.cr.commit()
sources = qa["portal.google.review.source"].search([])
parameters = qa["ir.config_parameter"].sudo()
report = {
    "target": "TEST", "database": env.cr.dbname,
    "qa_service_id": template.id, "card_price": template.website_card_price,
    "selling_prices_preserved": True,
    "label_en": template.with_context(lang="en_US").website_card_price_label,
    "label_ar": template.with_context(lang="ar_001").website_card_price_label,
    "google_source_count": len(sources),
    "google_authorized_source_count": len(sources.filtered(lambda s: s.enabled and s.location_name and s.client_id and s.client_secret and s.refresh_token)),
    "sms_credentials_configured": bool(parameters.get_param("infinito_client_id") and parameters.get_param("infinito_client_password")),
    "fixed_otp_bypass_enabled": parameters.get_param("portal_api.allow_test_otp") not in (False, "", "0", "False", "false"),
    "modules": qa["ir.module.module"].search([("name", "in", ["portal_content", "portal_api"])]).read(["name", "latest_version", "state"]),
}
print("WEBSITE_CARD_TEST=" + json.dumps(report, ensure_ascii=False, sort_keys=True))
