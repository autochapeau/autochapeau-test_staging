import json

from odoo import http
from odoo.http import request

from .common import authorization_required, check_params, make_json_response


class LoyaltyAPI(http.Controller):
    @http.route("/v1/loyalty/exchange", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_loyalty_exchange(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["points"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        points = data.get("points", 0)
        partner = request.env.user.partner_id
        try:
            partner.exchange_loyalty_points_to_wallet(points)
        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e)})
        response_data = {"message": "successfully changed points", "wallet_balance": partner.wallet_balance}
        return make_json_response(200, response_data)
