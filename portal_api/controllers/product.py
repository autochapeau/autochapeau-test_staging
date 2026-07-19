import json

from odoo import http
from odoo.http import request

from .common import (
    authorization_required,
    check_params,
    format_search_read_result,
    get_binary_url,
    make_json_response,
    make_response,
    with_lang,
)

FIELDS_READ = [
    "id",
    "name",
    "categ_id",
    "lst_price",
    "lst_price_discount",
    "expected_duration",
    "warranty",
    "description",
    "description_website",
    "feature_ids",
    "total_sales_count",
    "image_1920",
]


class ProductAPI(http.Controller):
    @http.route("/v1/categories", type="http", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_categories(self):
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["category_type"])
        if check_data:
            return make_json_response(422, check_data)
        try:
            fields_name = ["id", "name"]
            category_type = data.get("category_type")
            categories = (
                request.env["product.category"].sudo().search_read(
                    [("category_type", "=", category_type)], fields_name)
            )
            result = format_search_read_result(categories, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/services", type="http", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_services_by_vehicle(self):
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["vehicle_id"])
        if check_data:
            return make_json_response(422, check_data)
        vehicle_id = data.get("vehicle_id")
        model_id = data.get("model_id", False)
        pr_env = request.env["product.product"].sudo()
        pf_env = request.env["product.feature"].sudo()
        if vehicle_id != -1:
            vehicle = request.env["fleet.vehicle"].sudo().browse(
                int(data.get("vehicle_id")))
            services_domain = vehicle._get_available_service_domain()
        elif model_id:
            model = request.env["fleet.vehicle.model"].sudo().browse(
                int(model_id))
            services_domain = [
                ("detailed_type", "=", "service"),
                ("product_template_variant_value_ids.product_attribute_value_id.code", "=", model.size),
            ]
        else:
            services_domain = [
                ("detailed_type", "=", "service"),
                ("product_template_variant_value_ids.product_attribute_value_id.code", "=", "small"),
            ]
        # Forcer le filtre is_published = True
        services_domain.append(("is_published", "=", True))
        # Log the domain for debug
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(
            f"Domain used for services search: {services_domain}")
        services = pr_env.search_read(services_domain, FIELDS_READ)
        # Log after filtering
        _logger.info(f"Number of services after filtering: {len(services)}")
        for service in services:
            features = pf_env.search_read(
                [("id", "in", service.pop("feature_ids"))], ["name"])
            service["feature_ids"] = features
        result = format_search_read_result(
            services, FIELDS_READ, [], model_name="product.product")
        return make_response(200, result)

    @http.route("/v1/products", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_products(self):
        domain = [("detailed_type", "!=", "service"),
                  ("is_published", "=", True)]
        # Always return only published products, ignore is_published parameter
        products = request.env["product.product"].sudo(
        ).search_read(domain, FIELDS_READ)
        # Log after filtering
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Number of products after filtering: {len(products)}")
        pf_env = request.env["product.feature"].sudo()
        for product in products:
            features = pf_env.search_read(
                [("id", "in", product.pop("feature_ids"))], ["name"])
            product["feature_ids"] = features
        result = format_search_read_result(
            products, FIELDS_READ, [], model_name="product.product")
        return make_response(200, result)

    @http.route(
        "/v1/services/<int:service_id>", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*"
    )
    @with_lang
    def v1_product_details(self, service_id):
        fields = FIELDS_READ + \
            ["reviews_count", "reviews_rate",
                "review_ids", "question_ids", "image_ids"]
        product = request.env["product.product"].sudo(
        ).search_read([("id", "=", service_id)], fields)
        if not product:
            return make_response(404)
        result = format_search_read_result(
            product, fields, [], model_name="product.product")[0]
        # format feature_ids
        pf_env = request.env["product.feature"].sudo()
        features = pf_env.search_read(
            [("id", "in", result.pop("feature_ids"))], ["name"])
        result["feature_ids"] = features
        # format image_ids
        image_ids = result.get("image_ids", False)
        if image_ids:
            images = request.env["ir.attachment"].sudo().search_read(
                [("id", "in", image_ids)], ["datas"])
            images_url = format_search_read_result(
                images, ["datas"], [], model_name="ir.attachment")
            result.update({"image_ids": images_url})
        # format review_ids
        review_ids = result.get("review_ids", False)
        if review_ids:
            reviews_fields = ["create_date", "partner_id", "rate", "message"]
            reviews = (
                request.env["product.product.review"]
                .sudo()
                .search_read([("id", "in", review_ids), ("published", "=", True)], reviews_fields)
            )
            reviews_format = format_search_read_result(
                reviews, reviews_fields, [])
            result.update({"review_ids": reviews_format})
        # format question_ids
        question_ids = result.get("question_ids", False)
        if question_ids:
            questions_fields = ["question", "answer"]
            questions = (
                request.env["product.product.question"]
                .sudo()
                .search_read([("id", "in", question_ids)], questions_fields)
            )
            questions_format = format_search_read_result(
                questions, questions_fields, [])
            result.update({"question_ids": questions_format})
        return make_response(200, result)

    @http.route(
        "/v1/services/list", type="http", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @with_lang
    def v1_service_list(self):
        """List the services available for a car"""
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["vehicle_id"])
        if check_data:
            return make_response(422, check_data)
        vehicle_id = int(data.get("vehicle_id"))
        # vehicle_id == -1 (or unknown) "no vehicle": empty recordset so
        # no size filtering is applied (all published services are returned).
        vehicle = request.env["fleet.vehicle"].sudo().browse(
            vehicle_id).exists()
        templates = request.env["product.template"].sudo().search([
            ("detailed_type", "=", "service"),
            ("product_variant_ids.is_published", "=", True),
        ])
        result = []
        for t in templates:
            variants = t._get_published_variants_for_vehicle(vehicle)
            if not variants:
                continue
            # The cheapest variant is used as the "default" of the service:
            # its price, warranty and work hours are shown on the service card.
            default_variant = variants.sorted(key=lambda v: v.lst_price)[0]
            attributes = t.attribute_line_ids.attribute_id.with_context(
                lang="en_US")
            attr_keys = {a.id: (a.name or "").strip().lower().replace(
                " ", "_") for a in attributes}
            result.append({
                "id": t.id,
                "name": t.name,
                "categ_id": t.categ_id.name,
                "description": t.description or False,
                "description_website": t.description_website or False,
                "feature_ids": [{"id": f.id, "name": f.name} for f in t.feature_ids],
                "image_1920": get_binary_url("product.template", t.id, "image_1920") if t.image_1920 else False,
                # Default values (taken from the cheapest variant)
                "price_from": default_variant.lst_price,
                "lst_price_discount": default_variant.lst_price_discount,
                "warranty": default_variant.warranty,
                "work_hours": default_variant.expected_duration,
                "variant_count": len(variants),
                "variant_attributes": {
                    attr_keys[line.attribute_id.id]: {
                        "label": line.attribute_id.name,
                        "values": [{"id": v.id, "label": v.name} for v in line.value_ids],
                    }
                    for line in t.attribute_line_ids
                    # keep "size" selectable when there is no vehicle (id -1)
                    if attr_keys[line.attribute_id.id] != "size" or not vehicle.size
                },
                # Detailed list of every variant of the service
                "variants": [{
                    "id": v.id,
                    "name": v.display_name,
                    "attributes": {
                        attr_keys[ptav.attribute_id.id]: ptav.product_attribute_value_id.id
                        for ptav in v.product_template_variant_value_ids
                    },
                    "lst_price": v.lst_price,
                    "lst_price_discount": v.lst_price_discount,
                    "warranty": v.warranty,
                    "work_hours": v.expected_duration,
                } for v in variants],
            })
        return make_response(200, result)

    @http.route(
        "/v1/services/<int:service_id>/product-variants",
        type="http", auth="none", csrf=False,
        methods=["POST", "OPTIONS"], cors="*"
    )
    @with_lang
    def v1_service_product_variants(self, service_id):
        """Return the service  with its attributes and variants for a car"""
        template = request.env["product.template"].sudo().browse(
            service_id).exists()
        if not template:
            return make_response(200, [])
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["vehicle_id"])
        if check_data:
            return make_response(422, check_data)
        vehicle_id = int(data.get("vehicle_id"))
        # vehicle_id == -1 (or unknown) "no vehicle": empty recordset so
        # all variants are returned and the size attribute stays selectable.
        vehicle = request.env["fleet.vehicle"].sudo().browse(
            vehicle_id).exists()
        variants = template._get_published_variants_for_vehicle(vehicle)
        if not variants:
            return make_response(200, [])

        attributes = template.attribute_line_ids.attribute_id.with_context(
            lang="en_US")
        attr_keys = {a.id: (a.name or "").strip().lower().replace(
            " ", "_") for a in attributes}

        data = {
            "id": template.id,
            "name": template.name,
            "categ_id": template.categ_id.name,
            "description": template.description or False,
            "description_website": template.description_website or False,
            "feature_ids": [{"id": f.id, "name": f.name} for f in template.feature_ids],
            "image_1920": get_binary_url(
                "product.template", template.id, "image_1920") if template.image_1920 else False,
            "variant_attributes": {
                attr_keys[line.attribute_id.id]: {
                    "label": line.attribute_id.name,
                    "values": [{"id": v.id, "label": v.name} for v in line.value_ids],
                }
                for line in template.attribute_line_ids
                if attr_keys[line.attribute_id.id] != "size" or not vehicle.size
            },
            "variants": [{
                "id": v.id,
                "name": v.display_name,
                "attributes": {
                    attr_keys[ptav.attribute_id.id]: ptav.product_attribute_value_id.id
                    for ptav in v.product_template_variant_value_ids
                },
                "lst_price": v.lst_price,
                "lst_price_discount": v.lst_price_discount,
                "expected_duration": v.expected_duration,
                "warranty": v.warranty,
                "total_sales_count": v.total_sales_count,
                "is_published": v.is_published,
            } for v in variants],
        }
        return make_response(200, [data])

    @http.route("/v1/services/review", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_review_service(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["product_id", "rate", "message"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        try:
            data.update({"partner_id": request.env.user.partner_id.id})
            review = request.env["product.product.review"].sudo().create(data)
        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e)})
        response_data = {"message": "success", "review_id": review.id}
        return make_json_response(200, response_data)
