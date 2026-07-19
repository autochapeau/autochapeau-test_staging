from odoo import http
from odoo.http import request

from .common import authorization_required, make_response


class KeysAPI(http.Controller):
    @http.route("/v1/keys/hyperpay", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    def v1_get_hyperpay_keys(self):
        entity_id = request.env["ir.config_parameter"].sudo().get_param("HyperPay.entityId")
        entity_id_mada = request.env["ir.config_parameter"].sudo().get_param("HyperPay.entityIdMada")
        hyperpay_url = request.env["ir.config_parameter"].sudo().get_param("HyperPay.url")
        token = request.env["ir.config_parameter"].sudo().get_param("HyperPay.token")
        return make_response(200, {"entityId": entity_id, "entityIdMada": entity_id_mada, "url": hyperpay_url, "token": token})

    @http.route("/v1/keys/tabby", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    def v1_get_tabby_keys(self):
        merchant_code = request.env["ir.config_parameter"].sudo().get_param("tabby.merchant_code")
        secret_key = request.env["ir.config_parameter"].sudo().get_param("tabby.secret_key")
        currency = request.env["ir.config_parameter"].sudo().get_param("tabby.currency")
        max_amount_tabby_record = (
            request.env["res.config.settings"].sudo().search([("max_amount_tabby", "!=", False)], limit=1)
        )
        max_amount_value = max_amount_tabby_record.max_amount_tabby if max_amount_tabby_record else None
        return make_response(
            200,
            {
                "merchant_code": merchant_code,
                "secret_key": secret_key,
                "currency": currency,
                "max_amount_tabby": max_amount_value,
            },
        )

    @http.route("/v1/keys/mylist", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    def v1_get_mylist_keys(self):
        base_url = request.env["ir.config_parameter"].sudo().get_param("mylist.baseURL")
        token = request.env["ir.config_parameter"].sudo().get_param("mylist.Token")
        ip = request.env["ir.config_parameter"].sudo().get_param("mylist.IP")
        return make_response(200, {"baseURL": base_url, "Token": token, "IP": ip})

    @http.route("/v1/keys/yougotagift", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    def v1_get_yougotagift_keys(self):
        base_url = request.env["ir.config_parameter"].sudo().get_param("yougotagift.baseURL")
        yougotagift_username = request.env["ir.config_parameter"].sudo().get_param("yougotagift_username")
        yougotagift_password = request.env["ir.config_parameter"].sudo().get_param("yougotagift_password")
        return make_response(
            200, {"baseURL": base_url, "Password": yougotagift_password, "Username": yougotagift_username}
        )
