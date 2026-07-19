from odoo import http
from odoo.http import request

from .common import format_search_read_result, make_response, with_lang


class PortalContentsAPI(http.Controller):
    @http.route("/v1/portal/partners", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_partners(self):
        try:
            fields_name = ["id", "name", "summary", "image_1920"]
            records = request.env["portal.partner"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [], model_name="portal.partner")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route(
        "/v1/portal/loyalty_program", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*"
    )
    @with_lang
    def v1_get_loyalty_program(self):
        try:
            fields_name = ["id", "name", "summary", "details", "image_1920"]
            records = request.env["portal.loyalty.program"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [], model_name="portal.loyalty.program")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/testimonies", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_testimonies(self):
        try:
            fields_name = ["id", "name", "summary", "date", "image_1920"]
            records = request.env["portal.testimony"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [], model_name="portal.testimony")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/statistics", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_statistics(self):
        try:
            fields_name = ["id", "name", "value"]
            records = request.env["portal.statistic"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/news", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_news(self):
        try:
            fields_name = ["id", "name", "summary", "details", "date", "image_1920", "tag_ids"]
            records = request.env["portal.news"].sudo().search_read([], fields_name)
            tag_fields_name = ["id", "name"]
            for record in records:
                tags = request.env["portal.news.tag"].sudo().browse(record.pop("tag_ids"))
                tag_data = [{field: getattr(tag, field) for field in tag_fields_name} for tag in tags]
                record["tag_ids"] = tag_data
            result = format_search_read_result(records, fields_name, [], model_name="portal.news")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/aboutus", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_aboutus(self):
        try:
            fields_name = ["id", "name", "summary", "details", "image_1920"]
            records = request.env["portal.aboutus"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [], model_name="portal.aboutus")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/faq", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_faq(self):
        try:
            fields_name = ["id", "question", "answer"]
            records = request.env["portal.faq"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/offers", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_offers(self):
        try:
            fields_name = ["id", "name", "summary", "details", "image_1920"]
            records = request.env["portal.offer"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [], model_name="portal.offer")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/branches", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_branches(self):
        try:
            fields_name = ["id", "name", "address", "map_url", "image_1920"]
            records = request.env["portal.branch"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [], model_name="portal.branch")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/warranty", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_warranty(self):
        try:
            fields_name = ["id", "name", "details"]
            records = request.env["portal.warranty"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/privacy-policy", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_privacy_policy(self):
        try:
            fields_name = ["id", "name", "summary", "details"]
            records = request.env["portal.privacy.policy"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/return-change", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_return_change_policy(self):
        try:
            fields_name = ["id", "name", "summary", "details"]
            records = request.env["portal.return.change.policy"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route(
        "/v1/portal/terms-conditions", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*"
    )
    @with_lang
    def v1_get_terms_conditions(self):
        try:
            fields_name = ["id", "name", "summary", "details"]
            records = request.env["portal.terms.conditions"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/banners", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_banners(self):
        try:
            fields_name = ["id", "first_title", "second_title", "url"]
            records = request.env["portal.banner"].sudo().search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})
