"""Fictional TEST-only gallery fixture; never modifies an existing catalog item."""
import base64
import json
import os
from pathlib import Path
from odoo import Command

assert env.cr.dbname == "autochapeau_prod_test"
root = Path(os.environ["WEBSITE_QA_MEDIA_ROOT"])
fixture_id = "portal_api.website_qa_media_service"
service = env.ref(fixture_id, raise_if_not_found=False)
if not service:
    service = env["product.product"].with_context(tracking_disable=True, mail_create_nosubscribe=True).create({
        "name": "DEMO Website QA Media Service", "detailed_type": "service", "list_price": 1,
        "is_published": True, "description_website": "Fictional TEST gallery acceptance fixture"})
    env["ir.model.data"].create({"module": "portal_api", "name": "website_qa_media_service",
                               "model": "product.product", "res_id": service.id, "noupdate": True})
assert service.name == "DEMO Website QA Media Service"
service.image_1920 = base64.b64encode((root / "image-1.png").read_bytes())
attachments = env["ir.attachment"]
for filename, mimetype, field in (("image-2.png", "image/png", "image_ids"),
                                  ("demo-10s.mp4", "video/mp4", "video_ids")):
    attachment = attachments.search([("res_model", "=", "product.product"),
                                    ("res_id", "=", service.id), ("name", "=", filename)], limit=1)
    if not attachment:
        attachment = attachments.create({"name": filename, "mimetype": mimetype, "public": False,
            "res_model": "product.product", "res_id": service.id,
            "datas": base64.b64encode((root / filename).read_bytes())})
    service[field] = [Command.set(attachment.ids)]
env.cr.commit()
print("WEBSITE_MEDIA_FIXTURE=" + json.dumps({"template_id": service.product_tmpl_id.id,
    "product_id": service.id, "images": service.image_ids.ids, "videos": service.video_ids.ids,
    "attachments_remain_private": not any((service.image_ids | service.video_ids).mapped("public"))}))
