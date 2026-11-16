from odoo import http
from odoo.http import request

from .common import format_search_read_result, get_binary_url, make_response, with_lang


def _format_hour(value):
    value = value or 0.0
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:
        hours += 1
        minutes = 0
    return "%02d:%02d" % (hours % 24, minutes)


class PortalContentsAPI(http.Controller):
    @http.route("/v1/portal/partners", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_partners(self):
        try:
            fields_name = ["id", "name", "summary", "image_1920"]
            records = request.env["portal.partner"].sudo().with_context(bin_size=True).search_read([], fields_name)
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
            records = request.env["portal.loyalty.program"].sudo().with_context(bin_size=True).search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [], model_name="portal.loyalty.program")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/testimonies", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_testimonies(self):
        try:
            fields_name = ["id", "name", "summary", "date", "image_1920", "rating", "review_url", "profile_image_url"]
            sources = request.env["portal.google.review.source"].sudo().with_context(bin_size=True).search([("enabled", "=", True)])
            domain = [("google_source_id", "in", sources.ids), ("rating", "=", 5)] if sources else [("google_source_id", "=", False)]
            limit = max(sources.mapped("display_limit")) if sources else 10
            records = request.env["portal.testimony"].sudo().with_context(bin_size=True).search_read(domain, fields_name, limit=limit, order="review_time desc, date desc, id desc")
            result = format_search_read_result(records, fields_name, [], model_name="portal.testimony")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/statistics", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_statistics(self):
        try:
            fields_name = ["id", "name", "value", "metric", "code"]
            counters = request.env["portal.statistic"].sudo().with_context(bin_size=True).search([])
            legacy_codes = {"Satisfaction Rate": "satisfaction", "Number of cars": "cars", "Number of clients": "customers"}
            records = [{"id": counter.id, "name": counter.name, "value": counter._website_value(),
                        "metric": counter.metric,
                        "code": counter.metric if counter.metric != "manual" else legacy_codes.get(counter.with_context(lang="en_US").name, "manual")}
                       for counter in counters]
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/news", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_news(self):
        try:
            fields_name = ["id", "name", "summary", "details", "date", "image_1920", "tag_ids"]
            records = request.env["portal.news"].sudo().with_context(bin_size=True).search_read([], fields_name)
            tag_fields_name = ["id", "name"]
            for record in records:
                tags = request.env["portal.news.tag"].sudo().with_context(bin_size=True).browse(record.pop("tag_ids"))
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
            fields_name = ["id", "name", "summary", "details", "image_1920", "secondary_image"]
            records = request.env["portal.aboutus"].sudo().with_context(bin_size=True).search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [], model_name="portal.aboutus")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/faq", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_faq(self):
        try:
            fields_name = ["id", "question", "answer"]
            records = request.env["portal.faq"].sudo().with_context(bin_size=True).search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/offers", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_offers(self):
        try:
            fields_name = ["id", "name", "summary", "details", "image_1920", "is_main"]
            offers = request.env["portal.offer"].sudo().with_context(bin_size=True).search([])
            records = offers.read(fields_name)
            by_id = {offer.id: offer for offer in offers}
            for record in records:
                product = by_id[record["id"]].product_id
                published = product and product.active and product.sale_ok and product.is_published
                is_service = product.detailed_type == "service" if product else False
                record.update({
                    "product_id": product.id if published else False,
                    "catalog_id": (product.product_tmpl_id.id if is_service else product.id) if published else False,
                    "catalog_type": "service" if is_service else "product",
                    "purchasable": bool(published),
                })
            result = format_search_read_result(
                records, fields_name + ["product_id", "catalog_id", "catalog_type", "purchasable"],
                [], model_name="portal.offer",
            )
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/branches", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_branches(self):
        try:
            fields_name = ["id", "name", "address", "map_url", "image_1920"]
            branches = request.env["portal.branch"].sudo().with_context(bin_size=True).search([])
            records = [
                {
                    "id": branch.id,
                    "name": branch.name,
                    "address": branch.address or False,
                    "map_url": branch.map_url or False,
                    "image_1920": branch.image_1920,
                    "working_schedule": [
                        {
                            "day": line.day,
                            "hour_from": False if line.closed else _format_hour(line.hour_from),
                            "hour_to": False if line.closed else _format_hour(line.hour_to),
                            "closed": bool(line.closed),
                        }
                        for line in branch.schedule_ids
                    ],
                }
                for branch in branches
            ]
            result = format_search_read_result(records, fields_name + ["working_schedule"], [], model_name="portal.branch")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/warranty", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_warranty(self):
        try:
            fields_name = ["id", "name", "details"]
            records = request.env["portal.warranty"].sudo().with_context(bin_size=True).search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/privacy-policy", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_privacy_policy(self):
        try:
            fields_name = ["id", "name", "summary", "details"]
            records = request.env["portal.privacy.policy"].sudo().with_context(bin_size=True).search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/return-change", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_return_change_policy(self):
        try:
            fields_name = ["id", "name", "summary", "details"]
            records = request.env["portal.return.change.policy"].sudo().with_context(bin_size=True).search_read([], fields_name)
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
            records = request.env["portal.terms.conditions"].sudo().with_context(bin_size=True).search_read([], fields_name)
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/banners", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_banners(self):
        try:
            page = (request.httprequest.args.get("page") or "").strip()
            banner_model = request.env["portal.banner"].sudo().with_context(bin_size=True)
            domain = [("page_name", "=", page)] if page else []
            fields_name = ["id", "page_name", "first_title", "second_title", "url", "image_1920", "text_align", "text_position"]
            records = banner_model.search_read(domain, fields_name)
            language_image = "image_ar" if request.env.lang.startswith("ar") else "image_en"
            for record in records:
                banner = banner_model.browse(record["id"])
                if banner[language_image]:
                    record["image_1920"] = get_binary_url("portal.banner", banner.id, language_image)
            result = format_search_read_result(
                records, fields_name, [], model_name="portal.banner"
            )
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/theme", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_theme(self):
        try:
            fields_name = ["id", "name", "color", "date_start", "date_end", "is_current"]
            records = (
                request.env["portal.theme"]
                .sudo().with_context(bin_size=True)
                .search_read(
                    [("active", "=", True), ("is_current", "=", True)],
                    fields_name,
                    limit=1,
                )
            )
            result = format_search_read_result(records, fields_name, [])
            return make_response(200, result[0] if result else {})
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/home-section", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_home_section(self):
        try:
            section = request.env["portal.home.section"].sudo().with_context(bin_size=True).search([], limit=1)
            if not section:
                return make_response(200, {})
            thumbnail_url = False
            if section.image_1920:
                thumbnail_url = get_binary_url("portal.home.section", section.id, "image_1920")
            result = {
                "video_url": section.video_url or False,
                "video_thumbnail_url": thumbnail_url,
                "small_title": section.small_title or False,
                "title": section.title or False,
                "description": section.description or False,
                "items": [item.name for item in section.item_ids if item.name],
            }
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/care-section", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_care_section(self):
        try:
            section = request.env["portal.home.care"].sudo().with_context(bin_size=True).search([], limit=1)
            if not section:
                return make_response(200, {})
            items = []
            for item in section.item_ids:
                icon_url = False
                if item.image_1920:
                    icon_url = get_binary_url("portal.home.care.item", item.id, "image_1920")
                items.append(
                    {
                        "title": item.title or False,
                        "description": item.description or False,
                        "icon_url": icon_url,
                    }
                )
            result = {
                "title": section.title or False,
                "description": section.description or False,
                "items": items,
            }
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route(
        "/v1/portal/loyalty-section", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*"
    )
    @with_lang
    def v1_get_loyalty_section(self):
        try:
            section = request.env["portal.home.loyalty"].sudo().with_context(bin_size=True).search([], limit=1)
            if not section:
                return make_response(200, {})
            images = []
            for image in section.image_ids:
                image_url = False
                if image.image_1920:
                    image_url = get_binary_url("portal.home.loyalty.image", image.id, "image_1920")
                images.append(image_url)
            result = {
                "small_title": section.small_title or False,
                "title": section.title or False,
                "description": section.description or False,
                "subtitle": section.subtitle or False,
                "button_label": section.button_label or False,
                "button_url": section.button_url or False,
                "items": [item.name for item in section.item_ids if item.name],
                "images": images,
            }
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/portal/home-slider", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_home_slider(self):
        try:
            slides = request.env["portal.home.slider"].sudo().with_context(bin_size=True).search([])
            result = []
            for slide in slides:
                language_image = "image_ar" if request.env.lang.startswith("ar") else "image_en"
                image_field = language_image if slide[language_image] else "image_1920"
                if not slide[image_field]:
                    continue
                result.append(
                    {
                        "image_url": get_binary_url(
                            "portal.home.slider", slide.id, image_field
                        ),
                        "first_title": slide.first_title or False,
                        "second_title": slide.second_title or False,
                        "url": slide.url or False,
                        "overlay_opacity": slide.overlay_opacity,
                    }
                )
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})
