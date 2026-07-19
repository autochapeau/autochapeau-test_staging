
import json
import logging

from odoo import http
from odoo.http import request
from odoo.osv import expression

from .common import format_search_read_result, make_json_response, make_response, with_lang

_logger = logging.getLogger(__name__)

models_mapping = {
    "products": {"model": "product.product", "domain": [("detailed_type", "!=", "service")]},
    "services": {"model": "product.product", "domain": [("detailed_type", "=", "service")]},
    "offers": {"model": "portal.offer"},
    "news": {"model": "portal.news"},
    "partners": {"model": "portal.partner"},
    "branches": {"model": "res.company", "domain": [("parent_id", "!=", False)]},
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
    "offers": ["id", "name", "summary", "details", "image_1920"],
    "news": ["id", "name", "summary", "details", "date", "image_1920", "tag_ids"],
    "partners": ["id", "name", "summary", "image_1920"],
    "branches": ["id", "name"],
    "jobs": ["id", "name", "department_id", "no_of_recruitment", "description", "is_published"],
}


class PortalSearch(http.Controller):
    @http.route("/v1/portal/search", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @with_lang
    def v1_portal_search(self):
        try:
            data = json.loads(request.httprequest.data)
            # Accept an empty body or one without the 'name' key
            name = data.get("name", "")

            search_result = {}
            for key in models_mapping:
                fields_name = fields_mapping.get(key)
                model_name = models_mapping[key]["model"]
                search_domain = models_mapping[key].get("domain", [])
                # If 'name' is empty, do not filter by name
                if name:
                    search_domain = expression.AND(
                        [["name", "ilike", name], search_domain])
                records = request.env[model_name].sudo(
                ).search_read(search_domain, fields_name)
                result = format_search_read_result(
                    records, fields_name, [], model_name=model_name)
                if result:
                    search_result[key] = result
            return make_json_response(200, search_result)
        except Exception as e:
            return make_response(422, {"message": str(e)})
