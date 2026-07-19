import json
import logging

from odoo import http
from odoo.http import Response, content_disposition, request
from odoo.tools import ustr

from .common import authorization_required, check_params, make_json_response, with_lang

_logger = logging.getLogger(__name__)


class SaleOrderAPI(http.Controller):
    @http.route("/v1/shop", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_create_sale_order(self):
        def _prepare_line_with_discount(item_id, qty=1.0):
            """Prepare order line with discounted price if available."""
            product = request.env["product.product"].sudo().browse(item_id)
            line_vals = {
                "product_id": product.id,
                "product_uom_qty": qty,
            }
            # Apply discounted price if it exists and is lower than standard price
            discounted_price = product.lst_price_discount or 0.0
            if product.exists() and discounted_price > 0 and discounted_price < product.lst_price:
                line_vals["price_unit"] = discounted_price
            return (0, 0, line_vals)

        data = json.loads(request.httprequest.data)
        required_keys = ["company_id", "cart_id"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        optional_keys = ["vehicle_id", "appointment_slot_id", "branch_id"]
        sale_order_vals = {key: data.get(key)
                           for key in required_keys + optional_keys}
        # Si branch_id est fourni, lier la branche au sale.order
        if data.get("branch_id"):
            sale_order_vals["branch_id"] = data.get("branch_id")
        sale_order_vals["partner_id"] = request.env.user.partner_id.id
        order_lines = [(5, 0, 0)]
        # Add services with discount support
        order_lines.extend([
            _prepare_line_with_discount(service_id)
            for service_id in data.get("service_ids")
        ])
        # Add products with discount support
        order_lines.extend([
            _prepare_line_with_discount(product.get("id"), product.get("qty"))
            for product in data.get("products")
        ])
        sale_order_vals["order_line"] = order_lines
        try:
            sale_order = (
                request.env["sale.order"]
                .sudo()
                .search([("cart_id", "=", data.get("cart_id")), ("state", "=", "draft")])
            )
            if sale_order:
                sale_order.sudo().write(sale_order_vals)
            else:
                sale_order = request.env["sale.order"].sudo().create(
                    sale_order_vals)
        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e)})
        response_data = {"message": "success",
                         "sale_order_id": sale_order.id, "amount": sale_order.amount_total}
        return make_json_response(200, response_data)

    @http.route("/v1/shop/apply", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_shop_apply_coupon(self):
        """Apply loyalty program to a sale order.
        - if given coupon code (coupon , gift, promotion ) --> apply this code
        - if not given : use the partner loyalty card
        """
        data = json.loads(request.httprequest.data)
        required_keys = ["cart_id"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        cart_id = data.get("cart_id")
        coupon = data.get("coupon", False)
        partner = request.env.user.partner_id
        if not coupon:
            if partner.loyalty_card_id:
                coupon = partner.loyalty_card_id.code
            else:
                return make_json_response(422, {"message": "No rewards available for this customer!"})
        sale_order = request.env["sale.order"].sudo().search(
            [("cart_id", "=", cart_id), ("state", "=", "draft")])
        if not sale_order:
            return make_json_response(422, {"message": "Invalid Order ID"})
        amount_before_coupon = sale_order.amount_total
        # apply coupon
        status = sale_order._try_apply_code(coupon)
        if "error" in status:
            return make_json_response(422, {"message": str(status["error"])})
        if not status.values():
            return make_json_response(422, {"message": "No rewards available for this customer!"})
        for coupon_id, reward_id in status.items():
            sale_order._apply_program_reward(reward_id, coupon_id)
            sale_order._update_programs_and_rewards()
        response_data = {
            "message": "Coupon successfully applied",
            "order_id": sale_order.id,
            "discount_amount": amount_before_coupon - sale_order.amount_total,
            "order_amount": sale_order.amount_total,
        }
        return make_json_response(200, response_data)

    @http.route(
        "/v1/order/print/<string:access_token>",
        type="http",
        auth="public",
        methods=["GET", "OPTIONS"],
        website=True,
        cors="*",
    )
    @with_lang
    @authorization_required
    def print_order_report(self, access_token):
        try:
            order = request.env["sale.order"].sudo().search(
                [("access_token", "=", access_token)])
            if not order.exists():
                return Response(
                    ustr({"error": "Order not found"}),
                    headers=[("Content-Type", "application/json")],
                    status=404,
                )
            partner = order.partner_id.sudo()
            if request.params.get("lang") and request.params.get("lang") != partner.lang:
                partner.lang = request.params.get("lang")
            order = order.with_context(lang=partner.lang)
            report_service = request.env["ir.actions.report"].sudo()
            report, _ = report_service._render_qweb_pdf(
                "sale_pdf_quote_builder.action_report_saleorder_raw", [
                    order.id]
            )
            filename = "order_report.pdf"
            headers = [
                ("Content-Type", "application/pdf"),
                ("Content-Length", len(report)),
                ("Content-Disposition", content_disposition(filename)),
            ]
            return request.make_response(report, headers=headers)

        except Exception as e:
            _logger.exception(
                "API /v1/order/print: Error while generating report for access token %s: %s", access_token, ustr(
                    e)
            )
            return Response(ustr({"error": e}), headers=[("Content-Type", "application/json")], status=500)
