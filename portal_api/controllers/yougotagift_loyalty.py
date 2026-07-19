import json

from odoo import http
from odoo.http import request

from .common import authorization_required, make_json_response


class YouGotaGiftLoyaltyAPI(http.Controller):
    @http.route(
        "/v1/yougotagift/loyalty/history", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*"
    )
    @authorization_required
    def v1_yougotagift_loyalty_history(self):
        data = json.loads(request.httprequest.data)
        partner = request.env.user.partner_id.sudo()
        # Amount comes in negative value
        points_amount = float(data.get("amount"))
        partner.wallet_card_id.points += points_amount
        partner.loyalty_exchange_log_ids = [
            (
                0,
                0,
                {
                    "type": "yougotagift_loyalty_exchange",
                    "points": points_amount,
                    "amount": points_amount,
                    "card_destination_id": partner.wallet_card_id.id,
                },
            )
        ]
        response_data = {"message": "Success"}
        return make_json_response(200, response_data)
