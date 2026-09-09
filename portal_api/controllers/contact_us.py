import json

from odoo import SUPERUSER_ID, http
from odoo.http import request

from .common import check_params, check_request_body, make_json_response, make_response, with_lang


class ContactUs(http.Controller):
    @http.route(
        "/v1/contactus/countries", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*"
    )
    @with_lang
    def v1_get_contactus_countries(self):
        try:
            base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
            countries = (
                request.env["res.country"]
                .sudo()
                .search_read([], ["name", "code", "phone_code", "image_url"], order="name")
            )
            for country in countries:
                if country.get("image_url"):
                    country["image_url"] = f"{base_url}{country['image_url']}"
            return make_response(200, countries)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/contactus/cities", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_contactus_cities(self):
        try:
            country_id = request.httprequest.args.get("country_id")
            if not country_id:
                return make_response(422, {"message": "country_id missing"})
            try:
                country_id = int(country_id)
            except (TypeError, ValueError):
                return make_response(422, {"message": "country_id invalid"})
            cities = (
                request.env["res.city"]
                .sudo()
                .search_read(
                    [("country_id", "=", country_id)],
                    ["name", "country_id"],
                    order="name",
                )
            )
            result = [
                {
                    "id": city["id"],
                    "name": city["name"],
                    "country_id": city["country_id"][0] if city.get("country_id") else False,
                }
                for city in cities
            ]
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/contactus/tags", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_contactus_tags(self):
        try:
            tags = (
                request.env["crm.tag"]
                .sudo()
                .search_read([], ["id", "name", "color"], order="name")
            )
            return make_response(200, tags)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/contactus", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @check_request_body
    def v1_api_contactus(self):
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["name", "email_from", "subject", "description"])
        if check_data:
            return make_json_response(422, check_data)
        city = ''
        if data.get("city_id"):
            city_name = request.env['res.city'].sudo().search([('id', '=', data.get("city_id"))])
            city += city_name
        try:
            values = {
                "contact_name": data.get("name"),
                "mobile": data.get("phone"),
                "email_from": data.get("email_from"),
                "partner_name": data.get("partner_name"),
                "name": data.get("subject"),
                "description": data.get("description"),
                "country_id": data.get("country_id"),
                "city": city
            }
            request.env["crm.lead"].with_user(SUPERUSER_ID).create(values)
            return make_json_response(200, "Lead created successfully")
        except Exception as e:
            return make_json_response(500, {"message": e})
