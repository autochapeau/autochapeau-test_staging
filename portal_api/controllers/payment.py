# flake8: noqa: C901
import json
import logging
from datetime import datetime

import requests

from odoo import SUPERUSER_ID, fields, http
from odoo.http import Response, request
from odoo.tools import ustr

from .common import authorization_required, check_params, make_json_response, with_lang

_logger = logging.getLogger(__name__)


class PortalPayment(http.Controller):
    @http.route("/v1/payment", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_payment(self):
        def _to_float(value, default=0.0):
            try:
                return float(value if value not in (None, "") else default)
            except Exception:
                return float(default)

        user = request.env["res.users"].sudo().browse(request.uid)
        data = json.loads(request.httprequest.data)
        required_keys = ["cart_id", "amount", "payment_type", "loyalty_type"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        sale_order = request.env["sale.order"].sudo().search(
            [("cart_id", "=", data.get("cart_id"))], limit=1)
        if not sale_order:
            return make_json_response(400, "Cart does not exist")
        if sale_order.state not in ("draft", "sent"):
            return make_json_response(
                422,
                {
                    "message": f"The following orders are not in a state requiring confirmation: {sale_order.name}",
                },
            )
        sale_company = sale_order.company_id
        try:
            # Use the actual sale order amount (with discount applied)
            amount = float(sale_order.amount_total)
            donation_amount = _to_float(data.get("donation_amount"), 0.0)
            wallet_amount = _to_float(data.get("wallet_amount"), 0.0)

            payment_methods = request.env["payment.method"].sudo().search(
                [("code", "=", data.get("payment_type"))])
            if not payment_methods:
                return make_json_response(400, "Please Check Payment Type field")
            payment_method_id = payment_methods[0]
            # Consume the wallet points if customer pay order using wallet card
            if data.get("payment_type") == "wallet":
                wallet_card = sale_order.partner_id.wallet_card_id
                total_amount = amount + donation_amount
                wallet_card.points -= total_amount
                sale_order.partner_id.loyalty_exchange_log_ids = [
                    (
                        0,
                        0,
                        {
                            "type": "payment_by_wallet",
                            "points": total_amount,
                            "amount": total_amount,
                            "card_source_id": wallet_card.id,
                            "order_id": sale_order.id,
                        },
                    )
                ]
            # Create payment transaction and validated it
            provider = request.env.ref(
                "portal_api.payment_provider_portal_gateways").sudo()
            payment_journal = provider.journal_id or request.env["account.journal"].sudo().search(
                [
                    ("type", "in", ["bank", "cash"]),
                    ("company_id", "=", sale_company.id),
                ],
                limit=1,
            )
            if not payment_journal:
                return make_json_response(400, {"message": "Payment provider journal is not configured."})

            transaction_values = {
                "payment_method_id": payment_method_id.id,
                "amount": amount,
                "donation_amount": donation_amount,
                "wallet_amount": wallet_amount,
                "currency_id": sale_order.currency_id.id,
                "provider_id": provider.id,
                # 'operation': 'online_redirect',
                "partner_id": sale_order.partner_id.id,
                "sale_order_ids": [sale_order.id],
                "company_id": sale_company.id,
                "state": "done",
            }
            if data.get("transaction_id"):
                transaction_values["reference"] = data.get("transaction_id")
            transaction = request.env["payment.transaction"].sudo().create(
                transaction_values)
            # Create donation journal entry if donation amount is provided and donation account is set up

            if (
                data.get("donation_amount")
                and sale_company
                and sale_company.donation_debit_account_id
                and sale_company.donation_credit_account_id
                and sale_company.donation_journal_id
            ):
                donation_vals = {
                    "company_id": sale_company.id,
                    "journal_id": sale_company.donation_journal_id.id,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "account_id": sale_company.donation_debit_account_id.id,
                                "debit": transaction.donation_amount,
                                "credit": 0,
                                "currency_id": sale_company.currency_id.id,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "account_id": sale_company.donation_credit_account_id.id,
                                "debit": 0,
                                "credit": transaction.donation_amount,
                                "currency_id": sale_company.currency_id.id,
                            },
                        ),
                    ],
                }
                donation_move = request.env["account.move"].sudo().create(
                    donation_vals)
                transaction.donation_move_id = donation_move.id
            # Create customer payment and validated it
            payment_values = {
                "payment_type": "inbound",
                "contact_type": "customer",
                "amount": amount,
                "date": fields.Datetime.now(),
                # todo: check journal_id without a company_id
                "journal_id": payment_journal.id,
                "company_id": payment_journal.company_id.id,
                "payment_transaction_id": transaction.id,
                "partner_id": sale_order.partner_id.id,
            }
            # TODO: Replace SUPERUSER_ID with a user that has the correct access rights.
            payment = request.env["account.payment"].with_user(
                SUPERUSER_ID).create(payment_values)
            payment.with_user(SUPERUSER_ID).action_post()
            transaction.payment_id = payment.id
            if wallet_amount:
                wallet_card = sale_order.partner_id.wallet_card_id
                wallet_card.points -= wallet_amount
                sale_order.partner_id.loyalty_exchange_log_ids = [
                    (
                        0,
                        0,
                        {
                            "type": "payment_by_wallet",
                            "points": wallet_amount,
                            "amount": wallet_amount,
                            "card_source_id": wallet_card.id,
                            "order_id": sale_order.id,
                        },
                    )
                ]

            # Store destination; points are granted only when the invoice is paid.
            loyalty_type = data.get("loyalty_type") or "autochapeau"
            if loyalty_type not in ("autochapeau", "alrajhi", "qitaf"):
                return make_json_response(422, {"message": "Invalid loyalty_type"})
            sale_order.write({"loyalty_type": loyalty_type})
            if loyalty_type != "autochapeau":
                sale_order.coupon_point_ids.sudo().unlink()
            sale_order.with_user(SUPERUSER_ID).action_confirm()
            return make_json_response(200, {"message": "success"})
        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e)})

    @http.route("/v1/loyalty/retry_phone", type="json", auth="none", csrf=False, methods=["POST"], cors="*")
    @authorization_required
    def retry_loyalty_phone(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["order_id", "phone", "loyalty_type", "amount"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        order_id = data.get("order_id")
        amount = data.get("amount")
        new_phone = data.get("phone")
        loyalty_type = data.get("loyalty_type")

        if not order_id or not new_phone:
            return make_json_response(422, {"message": "Missing order_id or phone"})

        order = request.env["sale.order"].sudo().search(
            [("id", "=", order_id)])
        if not order:
            return make_json_response(404, {"message": "Order not found"})

        service = request.env["loyalty.earn.service"].sudo()
        if loyalty_type == "alrajhi":
            result = service.earn_alrajhi(
                new_phone,
                amount,
                branch_code=order.company_id.branch_code,
            )
        elif loyalty_type == "qitaf":
            result = service.earn_qitaf(new_phone, amount)
        else:
            return make_json_response(422, {"message": "Invalid loyalty_type"})

        if result.get("success"):
            # Mark related paid invoices as earned when retry succeeds.
            invoices = order.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice"
                and m.state == "posted"
                and m.payment_state in ("paid", "in_payment")
                and not m.loyalty_earn_done
            )
            invoices.write({"loyalty_earn_done": True, "loyalty_points_granted": float(amount or 0.0) or 1.0})
            return make_json_response(200, {"message": "Loyalty points added successfully with new phone"})
        return make_json_response(
            422,
            {"message": result.get("message") or "Failed to add loyalty points with new phone"},
        )

    @http.route(
        "/v1/invoice/print/<string:access_token>",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        website=True,
        cors="*",
    )
    @with_lang
    @authorization_required
    def print_invoice(self, access_token):
        try:
            invoice = request.env["account.move"].sudo().search(
                [("access_token", "=", access_token)])
            if not invoice.exists():
                return Response(
                    ustr({"error": "Invoice not found"}),
                    headers=[("Content-Type", "application/json")],
                    status=404,
                )
            partner = invoice.partner_id.sudo()
            if request.params.get("lang") and request.params.get("lang") != partner.lang:
                partner.lang = request.params.get("lang")
            invoice = invoice.with_context(lang=partner.lang)

            report_service = request.env["ir.actions.report"].sudo()
            pdf_content, _ = report_service._render_qweb_pdf(
                "account.account_invoices", [invoice.id])

            file_name = "invoice_%s.pdf" % invoice.name.replace("/", "_")
            headers = [
                ("Content-Type", "application/pdf"),
                ("Content-Length", str(len(pdf_content))),
                ("Content-Disposition", 'inline; filename="%s"' % file_name),
            ]
            return Response(pdf_content, headers=headers)
        except Exception as e:
            _logger.exception(
                "API /v1/invoice/print: Error while generating report for access token %s: %s", access_token, ustr(
                    e)
            )
            return Response(ustr({"error": e}), headers=[("Content-Type", "application/json")], status=500)
