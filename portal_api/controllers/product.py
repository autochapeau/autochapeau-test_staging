import json
import logging

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

_logger = logging.getLogger(__name__)

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

MAX_LIMIT = 100


def _parse_pagination(params, default_limit=20):
    """Return (page, limit, offset) from request params/body."""
    try:
        page = int(params.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(params.get("limit") or default_limit)
    except (TypeError, ValueError):
        limit = default_limit
    page = max(page, 1)
    limit = min(max(limit, 1), MAX_LIMIT)
    offset = (page - 1) * limit
    return page, limit, offset


def _paginated_response(items, total, page, limit):
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items,
    }


def _parse_ids(value):
    """Parse int / list / comma-separated string into a list of ints."""
    if value in (None, False, ""):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, (list, tuple)):
        ids = []
        for item in value:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return ids
    ids = []
    for part in str(value).replace(" ", "").split(","):
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


def _get_categ_ids(params):
    """Read categ_ids or categ_id from request params/body."""
    categ_ids = _parse_ids(params.get("categ_ids"))
    if not categ_ids:
        categ_ids = _parse_ids(params.get("categ_id"))
    return categ_ids


def _append_categ_domain(domain, categ_ids):
    """Filter by product category (includes child categories)."""
    if categ_ids:
        domain = list(domain) + [("categ_id", "child_of", categ_ids)]
    return domain


def _sizes_for_brand(brand_id):
    """Return vehicle model sizes for a fleet brand, or None if no brand filter."""
    if brand_id in (None, False, "", 0, "0"):
        return None
    try:
        brand_id = int(brand_id)
    except (TypeError, ValueError):
        return []
    models = (
        request.env["fleet.vehicle.model"]
        .sudo()
        .search([("brand_id", "=", brand_id)])
    )
    return [size for size in models.mapped("size") if size]


def _append_brand_size_domain(domain, brand_id):
    """
    Filter services by vehicle brand via model sizes.
    Used when no specific vehicle is selected.
    """
    sizes = _sizes_for_brand(brand_id)
    if sizes is None:
        return domain
    if not sizes:
        return list(domain) + [("id", "=", False)]
    return list(domain) + [
        (
            "product_template_variant_value_ids.product_attribute_value_id.code",
            "in",
            sizes,
        )
    ]


def _attach_features(records):
    pf_env = request.env["product.feature"].sudo()
    for record in records:
        features = pf_env.search_read([("id", "in", record.pop("feature_ids"))], ["name"])
        record["feature_ids"] = features
    return records


def _window_tinting_payload_from_template(template):
    """Return window-tinting options for a product.template."""
    if not template or not template.is_window_tinting:
        return {
            "is_window_tinting": False,
            "glass_types": [],
            "tint_percentages": [],
        }
    glass_types = template.allowed_glass_type_ids or request.env[
        "window.tint.glass.type"
    ].sudo().search([("active", "=", True)])
    tint_percentages = template.allowed_tint_percentage_ids or request.env[
        "window.tint.percentage"
    ].sudo().search([("active", "=", True)])
    return {
        "is_window_tinting": True,
        "glass_types": [
            {
                "id": glass.id,
                "name": glass.name,
                "sequence": glass.sequence,
            }
            for glass in glass_types
        ],
        "tint_percentages": [
            {
                "id": percent.id,
                "name": percent.name,
                "percentage": percent.percentage,
            }
            for percent in tint_percentages
        ],
    }


def _window_tinting_payload_from_product(product):
    """Return window-tinting options for a product.product."""
    if not product:
        return {
            "is_window_tinting": False,
            "glass_types": [],
            "tint_percentages": [],
        }
    return _window_tinting_payload_from_template(product.product_tmpl_id)


def _variant_attributes_payload(template, vehicle=None):
    """Build variant_attributes including price_extra per value.

    price_extra comes from product.template.attribute.value (Value Price Extra
    on the product), e.g. +500 for "ازالة عازل حراري = True".
    """
    attributes = template.attribute_line_ids.attribute_id.with_context(lang="en_US")
    attr_keys = {
        a.id: (a.name or "").strip().lower().replace(" ", "_")
        for a in attributes
    }
    vehicle_size = vehicle.size if vehicle else False
    ptav_by_pav = {
        ptav.product_attribute_value_id.id: ptav
        for ptav in template.attribute_line_ids.product_template_value_ids
    }

    variant_attributes = {}
    for line in template.attribute_line_ids:
        key = attr_keys.get(line.attribute_id.id)
        if not key:
            continue
        # keep "size" selectable when there is no vehicle size
        if key == "size" and vehicle_size:
            continue
        values = []
        for pav in line.value_ids:
            ptav = ptav_by_pav.get(pav.id)
            values.append(
                {
                    "id": pav.id,
                    "label": pav.name,
                    "price_extra": ptav.price_extra if ptav else 0.0,
                }
            )
        variant_attributes[key] = {
            "label": line.attribute_id.name,
            "values": values,
        }
    return attr_keys, variant_attributes


class ProductAPI(http.Controller):
    @http.route(
        "/v1/categories",
        type="http",
        auth="none",
        csrf=False,
        methods=["GET", "POST", "OPTIONS"],
        cors="*",
    )
    @with_lang
    def v1_get_categories(self):
        """Return Product Categories that have published products/services.

        GET  /v1/categories
        GET  /v1/categories?category_type=service|other
        POST /v1/categories  body: { "category_type": "service"|"other" }  (optional)
        """
        try:
            category_type = None
            if request.httprequest.method == "POST":
                raw = request.httprequest.data
                data = json.loads(raw) if raw else {}
                category_type = data.get("category_type") or None
            else:
                category_type = request.httprequest.args.get("category_type") or None

            if category_type and category_type not in ("service", "other"):
                return make_response(
                    422,
                    {
                        "message": "category_type must be 'service' or 'other'",
                    },
                )

            # Only categories used by published portal products/services
            product_domain = [("is_published", "=", True)]
            if category_type == "service":
                product_domain.append(("detailed_type", "=", "service"))
            elif category_type == "other":
                product_domain.append(("detailed_type", "!=", "service"))

            used_categ_ids = (
                request.env["product.product"]
                .sudo()
                .search(product_domain)
                .mapped("categ_id")
                .ids
            )
            if not used_categ_ids:
                return make_response(200, [])

            fields_name = ["id", "name", "category_type"]
            domain = [("id", "in", used_categ_ids)]
            if category_type:
                domain.append(("category_type", "=", category_type))
            categories = (
                request.env["product.category"]
                .sudo()
                .search_read(domain, fields_name, order="name")
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
        brand_id = data.get("brand_id", False)
        categ_ids = _get_categ_ids(data)
        page, limit, offset = _parse_pagination(data)
        pr_env = request.env["product.product"].sudo()
        # Specific vehicle wins over brand/model size filters
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
            ]
            # Optional brand filter (fleet brand → model sizes)
            services_domain = _append_brand_size_domain(services_domain, brand_id)
            # Backward compatible default when no vehicle/model/brand
            if brand_id in (None, False, "", 0, "0"):
                services_domain.append(
                    (
                        "product_template_variant_value_ids.product_attribute_value_id.code",
                        "=",
                        "small",
                    )
                )
        # Forcer le filtre is_published = True
        services_domain.append(("is_published", "=", True))
        services_domain = _append_categ_domain(services_domain, categ_ids)
        _logger.info("Domain used for services search: %s", services_domain)
        total = pr_env.search_count(services_domain)
        services = pr_env.search_read(services_domain, FIELDS_READ, limit=limit, offset=offset)
        _logger.info("Number of services after filtering: %s / total=%s", len(services), total)
        _attach_features(services)
        result = format_search_read_result(
            services, FIELDS_READ, [], model_name="product.product")
        return make_response(200, _paginated_response(result, total, page, limit))

    @http.route("/v1/products", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_products(self):
        params = request.httprequest.args
        domain = [("detailed_type", "!=", "service"),
                  ("is_published", "=", True)]
        domain = _append_categ_domain(domain, _get_categ_ids(params))
        page, limit, offset = _parse_pagination(params)
        product_env = request.env["product.product"].sudo()
        total = product_env.search_count(domain)
        products = product_env.search_read(domain, FIELDS_READ, limit=limit, offset=offset)
        _logger.info("Number of products after filtering: %s / total=%s", len(products), total)
        _attach_features(products)
        result = format_search_read_result(
            products, FIELDS_READ, [], model_name="product.product")
        return make_response(200, _paginated_response(result, total, page, limit))

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
            images = request.env["ir.attachment"].sudo().browse(image_ids).exists()
            # Ensure attachments are publicly streamable for website <img>
            private_images = images.filtered(lambda a: not a.public)
            if private_images:
                private_images.write({"public": True})
            # Keep key "datas" for the website; serve via /portal/image/.../raw
            result["image_ids"] = [
                {
                    "id": attachment.id,
                    "datas": get_binary_url("ir.attachment", attachment.id, "raw"),
                }
                for attachment in images
                if attachment.raw or attachment.datas
            ]
        else:
            result["image_ids"] = []
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
        # Window tinting options for website selectors
        product_rec = request.env["product.product"].sudo().browse(service_id)
        result.update(_window_tinting_payload_from_product(product_rec))
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
        brand_id = data.get("brand_id", False)
        categ_ids = _get_categ_ids(data)
        page, limit, offset = _parse_pagination(data)
        # vehicle_id == -1 (or unknown) "no vehicle": empty recordset so
        # no size filtering is applied (all published services are returned),
        # unless brand_id is provided (then filter by that brand's model sizes).
        vehicle = request.env["fleet.vehicle"].sudo().browse(
            vehicle_id).exists()
        template_domain = [
            ("detailed_type", "=", "service"),
            ("product_variant_ids.is_published", "=", True),
        ]
        template_domain = _append_categ_domain(template_domain, categ_ids)
        templates = request.env["product.template"].sudo().search(template_domain)
        brand_sizes = None if vehicle else _sizes_for_brand(brand_id)
        matched_templates = request.env["product.template"].sudo()
        for template in templates:
            variants = template._get_published_variants_for_vehicle(vehicle)
            if not variants:
                continue
            if brand_sizes is not None:
                if not brand_sizes:
                    continue
                variants = variants.filtered(
                    lambda v: any(
                        code in brand_sizes
                        for code in v.product_template_variant_value_ids.product_attribute_value_id.mapped("code")
                    )
                )
                if not variants:
                    continue
            matched_templates |= template
        total = len(matched_templates)
        page_templates = matched_templates[offset: offset + limit]
        result = []
        for t in page_templates:
            variants = t._get_published_variants_for_vehicle(vehicle)
            if brand_sizes:
                variants = variants.filtered(
                    lambda v: any(
                        code in brand_sizes
                        for code in v.product_template_variant_value_ids.product_attribute_value_id.mapped("code")
                    )
                )
            if not variants:
                continue
            # The cheapest variant is used as the "default" of the service:
            # its price, warranty and work hours are shown on the service card.
            default_variant = variants.sorted(key=lambda v: v.lst_price)[0]
            attr_keys, variant_attributes = _variant_attributes_payload(t, vehicle)
            result.append({
                "id": t.id,
                "name": t.name,
                "categ_id": t.categ_id.name,
                "description": t.description or False,
                "description_website": t.description_website or False,
                "feature_ids": [{"id": f.id, "name": f.name} for f in t.feature_ids],
                "image_1920": get_binary_url("product.template", t.id, "image_1920") if t.image_1920 else False,
                "is_window_tinting": bool(t.is_window_tinting),
                # Default values (taken from the cheapest variant)
                "price_from": default_variant.lst_price,
                "lst_price_discount": default_variant.lst_price_discount,
                "warranty": default_variant.warranty,
                "work_hours": default_variant.expected_duration,
                "variant_count": len(variants),
                "variant_attributes": variant_attributes,
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
        return make_response(200, _paginated_response(result, total, page, limit))

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

        attr_keys, variant_attributes = _variant_attributes_payload(template, vehicle)

        data = {
            "id": template.id,
            "name": template.name,
            "categ_id": template.categ_id.name,
            "description": template.description or False,
            "description_website": template.description_website or False,
            "feature_ids": [{"id": f.id, "name": f.name} for f in template.feature_ids],
            "image_1920": get_binary_url(
                "product.template", template.id, "image_1920") if template.image_1920 else False,
            "variant_attributes": variant_attributes,
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
        data.update(_window_tinting_payload_from_template(template))
        return make_response(200, [data])

    @http.route(
        "/v1/window-tinting/<int:product_id>",
        type="http",
        auth="none",
        csrf=False,
        methods=["GET", "OPTIONS"],
        cors="*",
    )
    @with_lang
    def v1_window_tinting_options(self, product_id):
        """Return glass types + tint percentages for a product/service variant."""
        product = request.env["product.product"].sudo().browse(product_id).exists()
        if not product:
            # Also accept product.template id (services/list uses template ids)
            template = (
                request.env["product.template"].sudo().browse(product_id).exists()
            )
            if not template:
                return make_response(404)
            payload = _window_tinting_payload_from_template(template)
            payload["product_id"] = False
            payload["product_tmpl_id"] = template.id
            return make_response(200, payload)

        payload = _window_tinting_payload_from_product(product)
        payload["product_id"] = product.id
        payload["product_tmpl_id"] = product.product_tmpl_id.id
        return make_response(200, payload)

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
