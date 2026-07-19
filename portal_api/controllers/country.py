from odoo import http
from odoo.http import request

from .common import make_response, with_lang


class CountryAPI(http.Controller):
    @http.route("/v1/countries", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def get_countries(self):
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        countries = request.env["res.country"].sudo().search_read([], ["name", "image_url", "code"])
        [
            country.update({"image_url": f"{base_url}{country['image_url']}"})
            for country in countries
            if country.get("image_url")
        ]
        return make_response(200, countries)
