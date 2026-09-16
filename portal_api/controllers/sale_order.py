import json
import logging

from odoo import http
from odoo.http import Response, content_disposition, request
from odoo.tools import ustr

from .common import (
    authorization_required,
    check_params,
    get_binary_url,
    make_json_response,
    make_response,
    with_lang,
)

_logger = logging.getLogger(__name__)


class SaleOrderAPI(http.Controller):
    def _prepare_tint_detail_commands(self, product, tint_details):
        """Build One2many commands for sale.order.line.tint.detail."""
        if not tint_details:
            return []
        if not product.product_tmpl_id.is_window_tinting:
            return []
        commands = []
        for idx, detail in enumerate(tint_details):
            glass_type_id = detail.get("glass_type_id")
            tint_percentage_id = detail.get("tint_percentage_id")
            if not glass_type_id or not tint_percentage_id:
                continue
            commands.append(
                (
                    0,
                    0,
                    {
                        "sequence": detail.get("sequence", (idx + 1) * 10),
                        "glass_type_id": int(glass_type_id),
                        "tint_percentage_id": int(tint_percentage_id),
                        "note": detail.get("note") or False,
                    },
                )
            )
        return commands

    def _prepare_line_with_discount(self, item_id, qty=1.0, tint_details=None):
        """Prepare order line with discounted price and optional tint details."""
        product = request.env["product.product"].sudo().browse(item_id)
        line_vals = {
            "product_id": product.id,
            "product_uom_qty": qty,
        }
        discounted_price = product.lst_price_discount or 0.0
        if product.exists() and discounted_price > 0 and discounted_price < product.lst_price:
            line_vals["price_unit"] = discounted_price
        tint_commands = self._prepare_tint_detail_commands(product, tint_details)
        if tint_commands:
            line_vals["tint_detail_ids"] = tint_commands
        return (0, 0, line_vals)

    def _find_partner_draft_cart(self, partner, cart_id=None):
        """Return the partner draft website cart (sale.order)."""
        SaleOrder = request.env["sale.order"].sudo()
        domain = [
            ("partner_id", "=", partner.id),
            ("state", "=", "draft"),
            ("cart_id", "!=", False),
        ]
        if cart_id:
            domain.append(("cart_id", "=", cart_id))
        return SaleOrder.search(domain, order="write_date desc, id desc", limit=1)

    def _serialize_cart(self, sale_order):
        """Payload compatible with website hydrateCart()."""
        if not sale_order:
            return {
                "cart_id": False,
                "sale_order_id": False,
                "company_id": False,
                "branch_id": False,
                "vehicle_id": False,
                "appointment_slot_id": False,
                "services": [],
                "products": [],
                "amount_total": 0.0,
            }

        services = []
        products = []
        for line in sale_order.order_line.filtered(lambda l: not l.display_type and l.product_id):
            product = line.product_id
            item = {
                "id": product.id,
                "name": product.display_name or product.name,
                "lst_price": product.lst_price,
                "lst_price_discount": product.lst_price_discount or 0.0,
                "expected_duration": product.expected_duration or 0.0,
                "image_1920": (
                    get_binary_url("product.product", product.id, "image_1920")
                    if product.image_1920
                    else False
                ),
                "is_window_tinting": bool(
                    getattr(product.product_tmpl_id, "is_window_tinting", False)
                ),
                "qty": line.product_uom_qty,
                "price_unit": line.price_unit,
                "price_subtotal": line.price_subtotal,
            }
            if hasattr(line, "tint_detail_ids") and line.tint_detail_ids:
                item["tint_details"] = [
                    {
                        "glass_type_id": detail.glass_type_id.id,
                        "glass_type_name": detail.glass_type_id.name,
                        "tint_percentage_id": detail.tint_percentage_id.id,
                        "tint_percentage_name": detail.tint_percentage_id.name,
                        "note": detail.note or False,
                    }
                    for detail in line.tint_detail_ids
                ]
            if product.detailed_type == "service":
                services.append(item)
            else:
                products.append(item)

        return {
            "cart_id": sale_order.cart_id,
            "sale_order_id": sale_order.id,
            "company_id": sale_order.company_id.id if sale_order.company_id else False,
            "branch_id": sale_order.branch_id.id if sale_order.branch_id else False,
            "vehicle_id": sale_order.vehicle_id.id if sale_order.vehicle_id else False,
            "appointment_slot_id": (
                sale_order.appointment_slot_id.id
                if sale_order.appointment_slot_id
                else False
            ),
            "services": services,
            "products": products,
            "amount_total": sale_order.amount_total,
        }

    def _sync_draft_cart(self, data):
        """Create/update a draft sale.order cart for the logged-in partner."""
        partner = request.env.user.partner_id
        cart_id = data.get("cart_id")
        if not cart_id:
            raise ValueError("cart_id is required")

        company_id = data.get("company_id") or request.env.user.company_id.id
        sale_order_vals = {
            "cart_id": cart_id,
            "partner_id": partner.id,
            "company_id": int(company_id) if company_id else False,
            "order_type": data.get("order_type") or "intern",
        }
        for key in ("vehicle_id", "appointment_slot_id", "branch_id"):
            if data.get(key):
                sale_order_vals[key] = data.get(key)

        order_lines = [(5, 0, 0)]
        services_payload = data.get("services")
        if services_payload:
            for service in services_payload:
                order_lines.append(
                    self._prepare_line_with_discount(
                        service.get("id"),
                        service.get("qty", 1.0),
                        service.get("tint_details") or service.get("tint_detail_ids"),
                    )
                )
        else:
            for service_id in data.get("service_ids") or []:
                order_lines.append(self._prepare_line_with_discount(service_id))

        for product in data.get("products") or []:
            order_lines.append(
                self._prepare_line_with_discount(
                    product.get("id"),
                    product.get("qty", 1.0),
                    product.get("tint_details") or product.get("tint_detail_ids"),
                )
            )
        sale_order_vals["order_line"] = order_lines

        sale_order = self._find_partner_draft_cart(partner, cart_id=cart_id)
        if not sale_order:
            # Reuse latest draft cart for this partner if cart_id changed locally
            sale_order = self._find_partner_draft_cart(partner)
            if sale_order:
                sale_order_vals["cart_id"] = cart_id

        if sale_order:
            sale_order.write(sale_order_vals)
        else:
            sale_order = request.env["sale.order"].sudo().create(sale_order_vals)
        return sale_order

    @http.route(
        "/v1/my/cart",
        type="http",
        auth="none",
        csrf=False,
        methods=["GET", "POST", "DELETE", "OPTIONS"],
        cors="*",
    )
    @authorization_required
    @with_lang
    def v1_my_cart(self):
        """Persist and restore the logged-in user's website cart.

        GET    /v1/my/cart       → current draft cart
        POST   /v1/my/cart       → create/update draft cart (no stock reservation)
        DELETE /v1/my/cart       → clear draft cart lines / cancel empty draft
        """
        partner = request.env.user.partner_id
        try:
            if request.httprequest.method == "GET":
                sale_order = self._find_partner_draft_cart(partner)
                return make_response(200, self._serialize_cart(sale_order))

            if request.httprequest.method == "DELETE":
                sale_order = self._find_partner_draft_cart(partner)
                if sale_order:
                    sale_order.order_line.unlink()
                    # Keep draft header so cart_id can be reused, or unlink if empty
                    sale_order.unlink()
                return make_response(
                    200,
                    {
                        "message": "Cart cleared",
                        **self._serialize_cart(False),
                    },
                )

            # POST
            raw = request.httprequest.data
            data = json.loads(raw) if raw else {}
            check_required = check_params(data, ["cart_id"])
            if check_required:
                return make_response(422, check_required)
            sale_order = self._sync_draft_cart(data)
            payload = self._serialize_cart(sale_order)
            payload["message"] = "Cart saved"
            return make_response(200, payload)
        except Exception as e:
            request.env.cr.rollback()
            _logger.exception("API /v1/my/cart failed: %s", e)
            return make_response(422, {"message": str(e)})

    @http.route("/v1/shop", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def v1_create_sale_order(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["company_id", "cart_id"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        optional_keys = ["vehicle_id", "appointment_slot_id", "branch_id"]
        sale_order_vals = {key: data.get(key)
                           for key in required_keys + optional_keys}
        if data.get("branch_id"):
            sale_order_vals["branch_id"] = data.get("branch_id")
        sale_order_vals["partner_id"] = request.env.user.partner_id.id
        sale_order_vals.setdefault("order_type", "intern")
        order_lines = [(5, 0, 0)]

        # Preferred: services as objects (supports tint_details)
        # Backward compatible: service_ids as plain ids
        services_payload = data.get("services")
        if services_payload:
            for service in services_payload:
                order_lines.append(
                    self._prepare_line_with_discount(
                        service.get("id"),
                        service.get("qty", 1.0),
                        service.get("tint_details") or service.get("tint_detail_ids"),
                    )
                )
        else:
            order_lines.extend([
                self._prepare_line_with_discount(service_id)
                for service_id in data.get("service_ids") or []
            ])

        for product in data.get("products") or []:
            order_lines.append(
                self._prepare_line_with_discount(
                    product.get("id"),
                    product.get("qty"),
                    product.get("tint_details") or product.get("tint_detail_ids"),
                )
            )

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
