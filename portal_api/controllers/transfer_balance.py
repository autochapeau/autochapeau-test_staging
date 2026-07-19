import json

from odoo import http
from odoo.http import request

from .common import authorization_required, check_params, check_request_body, make_json_response


class TransferBalanceApi(http.Controller):
    @http.route("/v1/transfer_balance", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @check_request_body
    @authorization_required
    def v1_transfer_balance(self):
        user = request.env["res.users"].sudo().browse(request.uid)
        data = json.loads(request.httprequest.data)
        required_keys = check_params(data, ["mobile", "amount"])
        if required_keys:
            return make_json_response(422, required_keys)
        try:
            mobile = data.get("mobile")
            amount = float(data.get("amount"))
            receiver = request.env["res.partner"].sudo().search([("phone", "=", mobile)], limit=1)
            sender = user.partner_id
            if not receiver:
                return make_json_response(404, {"message": "رقم الجوال غير صحيح أو غير مسجل."})
            if sender.wallet_balance < amount:
                return make_json_response(400, {"message": "الرصيد المتاح غير كافٍ لإتمام العملية."})

            sender.sudo().wallet_balance -= amount
            receiver.sudo().wallet_balance += amount

            return make_json_response(
                200,
                {
                    "message": "تم إهداء الرصيد بنجاح.",
                    "sender_new_balance": sender.wallet_balance,
                    "receiver_name": receiver.name,
                    "receiver_phone": receiver.phone,
                },
            )

        except Exception as e:
            return make_json_response(500, {"message": str(e)})
