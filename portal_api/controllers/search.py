
import json
import logging

from odoo import http
from odoo.http import request
from odoo.osv import expression

from .common import format_search_read_result, make_json_response, make_response, with_lang

_logger = logging.getLogger(__name__)

models_mapping = {
    "products": {"model": "product.product", "domain": [("detailed_type", "!=", "service"), ("is_published", "=", True), ("sale_ok", "=", True)]},
    "services": {"model": "product.product", "domain": [("detailed_type", "=", "service"), ("is_published", "=", True), ("sale_ok", "=", True)]},
    "offers": {"model": "portal.offer"},
    "news": {"model": "portal.news"},
    "partners": {"model": "portal.partner"},
    "branches": {"model": "portal.branch"},
    "faqs": {"model": "portal.faq", "search_field": "question"},
    "about": {"model": "portal.aboutus"},
    "loyalty": {"model": "portal.loyalty.program"},
    "warranty": {"model": "portal.warranty"},
    "privacy": {"model": "portal.privacy.policy"},
    "terms": {"model": "portal.terms.conditions"},
    "returns": {"model": "portal.return.change.policy"},
    # Add is_published filter for jobs
    "jobs": {"model": "hr.job", "domain": [("is_published", "=", True)]},
}
fields_mapping = {
    "products": [
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
        "image_1920",
    ],
    "services": [
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
        "image_1920",
    ],
    "offers": ["id", "name", "summary", "details", "image_1920", "is_main"],
    "news": ["id", "name", "summary", "details", "date", "image_1920", "tag_ids"],
    "partners": ["id", "name", "summary", "image_1920"],
    "branches": ["id", "name", "address", "image_1920"],
    "faqs": ["id", "question", "answer"],
    "about": ["id", "name", "summary"],
    "loyalty": ["id", "name", "summary"],
    "warranty": ["id", "name", "details"],
    "privacy": ["id", "name", "summary", "details"],
    "terms": ["id", "name", "summary", "details"],
    "returns": ["id", "name", "summary", "details"],
    "jobs": ["id", "name", "department_id", "no_of_recruitment", "description", "is_published"],
}


class PortalSearch(http.Controller):
    @http.route("/v1/portal/search", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @with_lang
    def v1_portal_search(self):
        try:
            data = json.loads(request.httprequest.data)
            # Accept an empty body or one without the 'name' key
            name = str(data.get("name") or "").strip()[:200]
            if not name:
                return make_json_response(200, {})

            search_result = {}
            for key in models_mapping:
                fields_name = fields_mapping.get(key)
                model_name = models_mapping[key]["model"]
                search_domain = models_mapping[key].get("domain", [])
                # If 'name' is empty, do not filter by name
                if name:
                    text_fields = [field for field in fields_name if field in
                                   ("name", "question", "answer", "summary", "details", "description", "description_website", "address")]
                    search_domain = expression.AND(
                        [expression.OR([[(field, "ilike", name)] for field in text_fields]), search_domain])
                records = request.env[model_name].sudo(
                ).search_read(search_domain, fields_name)
                result = format_search_read_result(
                    records, fields_name, [], model_name=model_name)
                if key == "services":
                    products = request.env[model_name].sudo().browse([row["id"] for row in result])
                    templates = {product.id: product.product_tmpl_id.id for product in products}
                    seen = set()
                    unique = []
                    for row in result:
                        template_id = templates[row["id"]]
                        if template_id not in seen:
                            seen.add(template_id)
                            row["id"] = template_id
                            unique.append(row)
                    result = unique
                if result:
                    search_result[key] = result
            return make_json_response(200, search_result)
        except Exception as e:
            return make_response(422, {"message": str(e)})
