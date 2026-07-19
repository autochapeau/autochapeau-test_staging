import json
import logging

import requests

from odoo import http
from odoo.http import request

from .common import authorization_required, check_params, make_json_response

_logger = logging.getLogger(__name__)


class Tabby(http.Controller):
    @http.route("/v1/tabby", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_payment(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["cart_id", "amount"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        secret_key = request.env["ir.config_parameter"].sudo().get_param("tabby.secret_key")
        checkout_api_url = request.env["ir.config_parameter"].sudo().get_param("tabby.checkout_api_url")
        headers = {
            "Authorization": "Bearer " + secret_key,
            "Content-Type": "application/json",
        }
        payload = self.get_tabby_payload(data)
        response = requests.post(checkout_api_url, data=payload, headers=headers, timeout=10)
        result = json.loads(response.content)
        if result["configuration"]["available_products"]:
            web_url = result["configuration"]["available_products"]["installments"][0]["web_url"]
            return make_json_response(200, {"web_url": web_url})
        else:
            return make_json_response(400, {"message": "Errors occurred while processing the request"})

    def get_tabby_payload(self, data):
        merchant_code = request.env["ir.config_parameter"].sudo().get_param("tabby.merchant_code")
        currency = request.env["ir.config_parameter"].sudo().get_param("tabby.currency")
        environment = request.env["ir.config_parameter"].sudo().get_param("tabby.environment")
        callback = request.env["ir.config_parameter"].sudo().get_param("tabby.callback")
        partner = request.env.user.partner_id
        amount = data.get("amount")
        cart_id = data.get("cart_id")
        sale_order = request.env["sale.order"].sudo().search([("cart_id", "=", cart_id)])
        if environment == "test":
            email = "card.success@tabby.ai"
            phone = "500000001"
        else:
            email = partner.email
            phone = partner.phone
        vals = {
            "payment": {
                "amount": f"{amount}",
                "currency": f"{currency}",
                "description": "",
                "buyer": {"phone": f"{phone}", "email": f"{email}", "name": f"{partner.name}", "dob": ""},
                "buyer_history": {
                    "registered_since": "2019-08-24T14:15:22Z",  # todo
                    "loyalty_level": 0,
                    "wishlist_count": 0,
                    "is_social_networks_connected": True,
                    "is_phone_number_verified": True,
                    "is_email_verified": True,
                },
                "order": {
                    "tax_amount": "0.00",
                    "shipping_amount": "0.00",
                    "discount_amount": "0.00",
                    "updated_at": "",  # todo  2019-08-24T14:15:22Z
                    "reference_id": f"{sale_order.name}",
                    "items": [
                        {
                            "title": f"{sale_order.name}",
                            "description": "",
                            "quantity": 1,
                            "unit_price": f"{amount}",
                            "discount_amount": "0.00",
                            "reference_id": "",
                            "image_url": "",
                            "product_url": "",
                            "gender": "",
                            "category": "Automotive",
                            "color": "",
                            "product_material": "",
                            "size_type": "",
                            "size": "",
                            "brand": "",
                        }
                    ],
                },
                "order_history": [
                    {
                        "purchased_at": "2019-08-24T14:15:22Z",  # todo
                        "amount": f"{amount}",
                        "payment_method": "card",
                        "status": "new",
                        "buyer": {
                            "phone": f"{partner.phone}",
                            "email": f"{email}",
                            "name": f"{partner.name}",
                            "dob": "",
                        },
                        "shipping_address": {
                            "city": f"{partner.city or 'city'}",
                            "address": f"{partner.street or 'address'}",
                            "zip": f"{partner.zip or 'zip'}",
                        },
                        # "items": [
                        #     {
                        #         "title": "string",
                        #         "description": "string",
                        #         "quantity": 1,
                        #         "unit_price": "0.00",
                        #         "discount_amount": "0.00",
                        #         "reference_id": "string",
                        #         "image_url": "http://example.com",
                        #         "product_url": "http://example.com",
                        #         "ordered": 0,
                        #         "captured": 0,
                        #         "shipped": 0,
                        #         "refunded": 0,
                        #         "gender": "Male",
                        #         "category": "string",
                        #         "color": "string",
                        #         "product_material": "string",
                        #         "size_type": "string",
                        #         "size": "string",
                        #         "brand": "string"
                        #     }
                        # ]
                    }
                ],
                "shipping_address": {
                    "city": f"{partner.city or 'city'}",
                    "address": f"{partner.street or 'address'}",
                    "zip": f"{partner.zip or 'zip'}",
                },
                "meta": {
                    # "order_id": "#1234",
                    # "customer": "#customer-id"
                },
                "attachment": {
                    # "body": "{\"flight_reservation_details\": {\"pnr\": \"TR9088999\","
                    #           " \"itinerary\": [...],\"insurance\": [...],\"passengers\": [...],"
                    #           " \"affiliate_name\": \"some affiliate\"}}",
                    # "content_type": "application/vnd.tabby.v1+json"
                },
            },
            "lang": "ar",
            "merchant_code": f"{merchant_code}",
            "merchant_urls": {
                "success": f"{callback}/?cart_id={cart_id}&amount={amount}",
                "cancel": f"{callback}",
                "failure": f"{callback}",
            },
        }
        return json.dumps(vals)
