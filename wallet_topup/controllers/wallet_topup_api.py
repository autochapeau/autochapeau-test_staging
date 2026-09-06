# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request
from odoo.addons.portal_api.controllers.common import (
    authorization_required,
    check_params,
    make_json_response,
    make_response,
)

_logger = logging.getLogger(__name__)

ALLOWED_BRANDS = ("visa", "mada", "applepay", "googlepay", "stc")


class WalletTopupAPI(http.Controller):
    @http.route(
        "/v1/wallet/topup/prepare",
        type="json",
        auth="none",
        csrf=False,
        methods=["POST", "OPTIONS"],
        cors="*",
    )
    @authorization_required
    def v1_wallet_topup_prepare(self):
        data = json.loads(request.httprequest.data or "{}")
        check_required = check_params(data, ["amount", "payment_brand"])
        if check_required:
            return make_json_response(422, check_required)

        try:
            amount = float(data.get("amount"))
        except (TypeError, ValueError):
            return make_json_response(422, {"message": "Invalid amount"})
        if amount <= 0:
            return make_json_response(422, {"message": "amount must be greater than zero"})

        brand = (data.get("payment_brand") or "").strip().lower()
        if brand not in ALLOWED_BRANDS:
            return make_json_response(
                422,
                {
                    "message": "Invalid payment_brand",
                    "allowed": list(ALLOWED_BRANDS),
                },
            )

        partner = request.env.user.partner_id.commercial_partner_id
        if not partner:
            return make_json_response(400, {"message": "No partner linked to this user"})

        topup = (
            request.env["wallet.topup.request"]
            .sudo()
            .create(
                {
                    "partner_id": partner.id,
                    "company_id": request.env.company.id,
                    "amount": amount,
                    "payment_brand": brand,
                    "state": "pending",
                }
            )
        )
        return make_json_response(
            200,
            {
                "message": "top-up prepared",
                "topup_id": topup.id,
                "topup_name": topup.name,
                "amount": topup.amount,
                "payment_brand": topup.payment_brand,
                "wallet_balance": partner.wallet_balance,
            },
        )

    @http.route(
        "/v1/wallet/topup/confirm",
        type="json",
        auth="none",
        csrf=False,
        methods=["POST", "OPTIONS"],
        cors="*",
    )
    @authorization_required
    def v1_wallet_topup_confirm(self):
        data = json.loads(request.httprequest.data or "{}")
        check_required = check_params(data, ["topup_id", "transaction_id"])
        if check_required:
            return make_json_response(422, check_required)

        try:
            topup_id = int(data.get("topup_id"))
        except (TypeError, ValueError):
            return make_json_response(422, {"message": "Invalid topup_id"})

        transaction_id = str(data.get("transaction_id") or "").strip()
        if not transaction_id:
            return make_json_response(422, {"message": "transaction_id required"})

        partner = request.env.user.partner_id.commercial_partner_id
        topup = request.env["wallet.topup.request"].sudo().browse(topup_id)
        if not topup.exists() or topup.partner_id.commercial_partner_id != partner:
            return make_json_response(404, {"message": "Top-up request not found"})

        if topup.state == "done":
            return make_json_response(
                200,
                {
                    "message": "already processed",
                    "topup_id": topup.id,
                    "topup_name": topup.name,
                    "amount": topup.amount,
                    "payment_brand": topup.payment_brand,
                    "transaction_id": topup.transaction_id,
                    "wallet_balance": partner.wallet_balance,
                },
            )

        try:
            topup.action_confirm_website_payment(transaction_id)
        except Exception as error:
            request.env.cr.rollback()
            _logger.exception("Wallet top-up confirm failed for %s", topup_id)
            return make_json_response(422, {"message": str(error)})

        partner.invalidate_recordset(["wallet_balance"])
        return make_json_response(
            200,
            {
                "message": "wallet topped up",
                "topup_id": topup.id,
                "topup_name": topup.name,
                "amount": topup.amount,
                "payment_brand": topup.payment_brand,
                "transaction_id": topup.transaction_id,
                "wallet_balance": partner.wallet_balance,
                "payment_id": topup.payment_id.id,
                "exchange_log_id": topup.exchange_log_id.id,
            },
        )

    @http.route(
        "/v1/wallet/topup/brands",
        type="http",
        auth="none",
        csrf=False,
        methods=["GET", "OPTIONS"],
        cors="*",
    )
    @authorization_required
    def v1_wallet_topup_brands(self):
        """List supported payment brands for website UI."""
        brands = [
            {"code": "visa", "name": "Visa", "hyperpay_brands": "VISA MASTER"},
            {"code": "mada", "name": "Mada", "hyperpay_brands": "MADA"},
            {"code": "applepay", "name": "Apple Pay", "hyperpay_brands": "APPLEPAY"},
            {"code": "googlepay", "name": "Google Pay", "hyperpay_brands": "GOOGLEPAY"},
            {"code": "stc", "name": "STC Pay", "hyperpay_brands": "STC_PAY"},
        ]
        return make_response(200, {"brands": brands})
