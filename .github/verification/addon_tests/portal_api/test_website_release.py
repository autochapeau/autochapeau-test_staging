import base64
from contextlib import ExitStack
from datetime import datetime
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from lxml import etree

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user
from odoo.addons.portal_api.controllers import binary, common, maintenance, portal_contents, product, search, vehicle


@tagged("post_install", "-at_install", "website_release")
class TestWebsiteRelease(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_create_nosubscribe=True))
        image = io.BytesIO()
        Image.new("RGB", (32, 32), "purple").save(image, format="PNG")
        cls.image = base64.b64encode(image.getvalue())
        cls.owner = new_test_user(cls.env, login="website-release-owner", groups="base.group_portal")
        cls.other = new_test_user(cls.env, login="website-release-other", groups="base.group_portal")
        cls.branch = cls.env["hr.department"].create({"name": "Website QA Branch", "department_type": "branche"})
        cls.warehouse = cls.env["stock.warehouse"].create({"name": "Website QA Warehouse", "code": "WREL", "branch_id": cls.branch.id})
        cls.staff = cls.env["hr.employee"].create({"name": "Website QA Technician", "is_technician": True, "branch_id": cls.branch.id})
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Website QA Brand"})
        model = cls.env["fleet.vehicle.model"].create({"name": "Website QA Car", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "license_plate": "WEB-QA"})
        cls.service = cls.env["product.product"].create({"name": "Website QA Service", "detailed_type": "service", "is_published": True})
        cls.film = cls.env["product.product"].create({"name": "Website QA Material", "detailed_type": "product", "standard_price": 10})
        cls.part = cls.env["car.part"].create({"name": "Website QA Window"})
        cls.env["car.service.part"].create({"service_id": cls.service.id, "part_id": cls.part.id,
            "component_ids": [Command.create({"product_id": cls.film.id, "quantity": 1})]})
        cls.env["stock.quant"]._update_available_quantity(cls.film, cls.warehouse.lot_stock_id, 20)

    def call(self, controller, name, env=None, method="GET", args=None, body=None, **kwargs):
        fake_request = SimpleNamespace(env=env or self.env,
            httprequest=SimpleNamespace(method=method, args=args or {}, data=json.dumps(body or {}).encode()))
        function = getattr(type(controller), name)
        while hasattr(function, "__wrapped__"):
            function = function.__wrapped__
        with ExitStack() as stack:
            for module in (common, maintenance, portal_contents, product, binary, search, vehicle):
                stack.enter_context(patch.object(module, "request", fake_request))
            response = function(controller, **kwargs)
            return response.status_code, json.loads(response.get_data())

    def issued_order(self):
        sale = self.env["sale.order"].create({"partner_id": self.owner.partner_id.id,
            "vehicle_id": self.vehicle.id, "order_type": "intern", "branch_id": self.branch.id,
            "warehouse_id": self.warehouse.id,
            "order_line": [Command.create({"product_id": self.service.id, "price_unit": 500})]})
        sale.state = "sale"
        order = self.env["car.work.order"].create({"partner_id": self.owner.partner_id.id,
            "vehicle_id": self.vehicle.id, "branch_id": self.branch.id,
            "sale_order_id": sale.id, "service_ids": [Command.create({"product_id": self.service.id,
                "staff_ids": [Command.set(self.staff.ids)]})]})
        order.picking_id = order._create_delivery_picking()
        order.state = "confirmed"
        order.action_start_materials()
        order.action_finish_materials()
        return sale, order

    def test_optional_banner_title_and_localized_image(self):
        banner = self.env["portal.banner"].create({"page_name": "website-qa", "image_ar": self.image,
            "image_en": self.image, "text_align": "left", "text_position": "bottom"})
        self.assertFalse(banner.first_title)
        status, rows = self.call(portal_contents.PortalContentsAPI(), "v1_get_banners",
            env=self.env(context=dict(self.env.context, lang="ar_001")), args={"page": "website-qa"})
        self.assertEqual(status, 200)
        self.assertIn("/image_ar?db=", rows[0]["image_1920"])
        self.assertEqual(rows[0]["text_align"], "left")
        self.assertEqual(rows[0]["text_position"], "bottom")

    def test_about_images_are_independent(self):
        item = self.env["portal.aboutus"].create({"name": "Website QA About", "image_1920": self.image,
                                                "secondary_image": self.image})
        item.image_1920 = False
        self.assertTrue(item.secondary_image)

    def test_overlay_accepts_zero_and_rejects_invalid_values(self):
        slide = self.env["portal.home.slider"].create({"image_1920": self.image, "overlay_opacity": 0})
        self.assertEqual(slide.overlay_opacity, 0)
        for invalid in (-0.01, 1.01):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                slide.overlay_opacity = invalid

    def test_offer_links_service_to_its_catalog_template(self):
        offer = self.env["portal.offer"].create({"name": "Website QA Offer", "product_id": self.service.id})
        status, rows = self.call(portal_contents.PortalContentsAPI(), "v1_get_offers")
        row = next(row for row in rows if row["id"] == offer.id)
        self.assertEqual(status, 200)
        self.assertTrue(row["purchasable"])
        self.assertEqual(row["catalog_id"], self.service.product_tmpl_id.id)
        self.assertEqual(row["catalog_type"], "service")
        self.service.is_published = False
        _, rows = self.call(portal_contents.PortalContentsAPI(), "v1_get_offers")
        self.assertFalse(next(row for row in rows if row["id"] == offer.id)["purchasable"])

    def test_gallery_includes_service_images_without_publishing_other_files(self):
        image = self.env["ir.attachment"].create({"name": "Website QA Gallery", "datas": self.image, "mimetype": "image/png"})
        secret = self.env["ir.attachment"].create({"name": "Website QA Private", "datas": self.image, "mimetype": "image/png"})
        self.service.image_ids = [Command.set(image.ids)]
        status, rows = self.call(product.ProductAPI(), "v1_service_product_variants", method="POST",
            body={"vehicle_id": -1}, service_id=self.service.product_tmpl_id.id)
        self.assertEqual(status, 200)
        self.assertEqual([row["id"] for row in rows[0]["image_ids"]], image.ids)
        fake = SimpleNamespace(env=self.env)
        with patch.object(binary, "request", fake):
            self.assertTrue(binary._attachment_is_public(image))
            self.assertFalse(binary._attachment_is_public(secret))
        self.assertFalse(image.public)
        self.assertFalse(secret.public)

    def test_category_summary_keeps_icons_and_omits_heavy_product_rows(self):
        self.service.categ_id = self.env["product.category"].create({"name": "Website QA Category", "portal_image": self.image})
        status, rows = self.call(product.ProductAPI(), "v1_get_categories_tree", args={"category_type": "service", "summary": "1"})
        def flatten(nodes):
            for node in nodes:
                yield node
                yield from flatten(node.get("children", []))
        row = next(row for row in flatten(rows) if row["id"] == self.service.categ_id.id)
        self.assertEqual(status, 200)
        self.assertTrue(row["image_url"])
        self.assertEqual(row["products"], [])
        self.assertEqual(row["product_count"], 1)

    def test_search_excludes_unpublished_products_and_returns_faqs(self):
        unpublished = self.env["product.product"].create({"name": "WebsiteQASearch Hidden", "is_published": False})
        published = self.env["product.product"].create({"name": "WebsiteQASearch Public", "is_published": True})
        faq = self.env["portal.faq"].create({"question": "WebsiteQASearch question", "answer": "A public answer"})
        status, body = self.call(search.PortalSearch(), "v1_portal_search", method="POST", body={"name": "WebsiteQASearch"})
        self.assertEqual(status, 200)
        self.assertIn(published.id, [row["id"] for row in body["products"]])
        self.assertNotIn(unpublished.id, [row["id"] for row in body["products"]])
        self.assertIn(faq.id, [row["id"] for row in body["faqs"]])

    def test_google_import_is_idempotent_and_retires_downgraded_reviews(self):
        source = self.env["portal.google.review.source"].create({"name": "Website QA Google", "location_name": "accounts/123/locations/456"})
        review = {"reviewId": "qa-review", "starRating": "FIVE", "createTime": "2026-01-01T12:00:00Z",
                  "comment": "Good service", "reviewer": {"displayName": "QA reviewer"}}
        source._apply_reviews([review])
        source._apply_reviews([review])
        rows = self.env["portal.testimony"].with_context(active_test=False).search([("google_source_id", "=", source.id)])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows.active)
        source._apply_reviews([{**review, "starRating": "FOUR"}])
        self.assertFalse(rows.active)

    def test_maintenance_is_scoped_to_order_owner_and_uses_issued_parts(self):
        sale, order = self.issued_order()
        customer_env = self.env(user=self.owner.id)
        status, data = self.call(maintenance.WebsiteMaintenance(), "maintenance", env=customer_env, order_id=sale.id)
        self.assertEqual(status, 200)
        self.assertEqual(data["services"][0]["parts"][0]["id"], self.part.id)
        status, _ = self.call(maintenance.WebsiteMaintenance(), "maintenance", env=self.env(user=self.other.id), order_id=sale.id)
        self.assertEqual(status, 404)
        values = {"service_line_id": sale.order_line.id, "source_task_id": order.service_ids.id,
                  "part_ids": self.part.ids, "description": "Website QA maintenance issue"}
        status, created = self.call(maintenance.WebsiteMaintenance(), "maintenance", env=customer_env,
            method="POST", order_id=sale.id, body=values)
        self.assertEqual(status, 201, created)
        claim = self.env["maintenance.claim"].browse(created["id"])
        self.assertEqual(claim.origin_sale_id, sale)
        self.assertEqual(claim.website_request_user_id, self.owner)
        self.assertEqual(claim.state, "quality")
        self.assertFalse(claim.move_id)
        status, _ = self.call(maintenance.WebsiteMaintenance(), "maintenance", env=customer_env,
            method="POST", order_id=sale.id, body=values)
        self.assertEqual(status, 409)

    def test_live_counters_preserve_opening_balance_and_unique_cars(self):
        _, first = self.issued_order()
        _, second = self.issued_order()
        (first | second).service_ids.write({"state": "done", "date_end": datetime(2100, 1, 1)})
        counter = self.env["portal.statistic"].create({"name": "Website QA Count", "value": "legacy",
            "metric": "cars", "opening_value": 10, "count_from": datetime(2099, 12, 31)})
        self.assertEqual(counter._website_value(), "11")
        counter.car_count_mode = "visits"
        self.assertEqual(counter._website_value(), "12")
        counter.metric = "customers"
        self.assertEqual(counter._website_value(), "11")
        counter.metric = "services"
        self.assertEqual(counter._website_value(), "12")
