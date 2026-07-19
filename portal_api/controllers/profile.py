import json
from datetime import datetime, timedelta

import pytz

from odoo import http
from odoo.http import request
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT as DEFAULT_DATETIME_FORMAT

from .common import (
    authorization_required,
    check_params,
    convert_utc_to_timezone,
    format_search_read_result,
    make_json_response,
    make_response,
    with_lang,
)
from .signup import generateOTP
from .sms import send_sms


class ProfileAPI(http.Controller):
    @http.route("/v1/titles", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @with_lang
    def v1_get_titles(self):
        titles = request.env["res.partner.title"].sudo().search_read([], [
            "name"])
        return make_response(200, titles)

    @http.route("/v1/my/profile", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    @with_lang
    def v1_my_profile(self):
        fields = [
            "title",
            "name",
            "phone",
            "email",
            "birthdate",
            "street",
            "street2",
            "country_id",
            "city",
            "image_1920",
        ]
        user = request.env["res.users"].sudo().search_read(
            [("id", "=", request.env.user.id)], fields)
        result = format_search_read_result(
            user, fields, [], model_name="res.users")[0]
        partner = request.env.user.partner_id
        membership = partner.membership_id
        result.update(
            {
                "loyalty_balance": partner.loyalty_balance,
                "expiration_date_loyalty": partner.loyalty_card_id.expiration_date,
                "wallet_balance": partner.wallet_balance,
                "membership": {
                    "code": membership.code,
                    "name": membership.name,
                } if membership else False,
            }
        )
        return make_response(200, result)

    @http.route("/v1/send/otp/profile", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @authorization_required
    def edit_my_profile(self):
        data = json.loads(request.httprequest.data)
        try:
            phone = data.get("phone")
            email = data.get("email")
            user = request.env["res.users"].sudo().browse(request.uid)
            send_to_phone = phone and phone != user.phone
            send_to_email = email and email != user.email

            if not send_to_phone and not send_to_email:
                USER_FIELDS_READ = [
                    "title",
                    "name",
                    "birthdate",
                    "street",
                    "street2",
                    "image_1920",
                    "country_id",
                    "city",
                ]
                update_data = {key: value for key,
                               value in data.items() if key in USER_FIELDS_READ}
                user.write(update_data)
                return make_json_response(200, {"message": "تم تعديل البيانات بنجاح."})

            if send_to_phone and request.env["res.users"].sudo().search([("phone", "=", phone), ("id", "!=", user.id)]):
                return make_json_response(400, {"message": "رقم الهاتف مستخدم بالفعل."})

            if send_to_email and request.env["res.users"].sudo().search([("email", "=", email), ("id", "!=", user.id)]):
                return make_json_response(400, {"message": "البريد الإلكتروني مستخدم بالفعل."})
            otp = generateOTP()
            now = datetime.now()
            deadline = now - timedelta(minutes=2)
            timezone = pytz.timezone(user.tz or "UTC")

            if not user.login_sms_date or user.login_sms_date < deadline:
                user.write({"last_otp": otp, "login_sms_date": now})
                if send_to_phone:
                    send_sms(phone, f"رمز التحقق الخاص بك هو: {otp}")
                if send_to_email:
                    template = request.env.ref("portal_api.mail_template_otp_profile")
                    template.sudo().send_mail(user.id, force_send=True, email_values={"email_to": email})
                return make_json_response(200, {"message": "تم إرسال رمز التحقق.", "time_left": 120})
            else:
                retry_time = (user.login_sms_date.astimezone(
                    timezone) + timedelta(minutes=2)).strftime("%H:%M:%S")
                time_left = int(
                    (
                        user.login_sms_date.astimezone(
                            timezone) + timedelta(minutes=2) - datetime.now(timezone)
                    ).total_seconds()
                )
                message = f"إذا لم تتلقى كود التحقق يمكنك المحاولة مرة أخرى بعد الساعة {retry_time}"
                return make_json_response(401, {"message": message, "time_left": time_left})

        except Exception as e:
            return make_json_response(500, {"message": str(e)})

    @http.route(
        "/v1/my/profile/edit",
        type="json",
        auth="none",
        csrf=False,
        methods=["POST", "OPTIONS"],
        cors="*",
    )
    @authorization_required
    def v1_verify_otp_profile(self):
        try:
            data = json.loads(request.httprequest.data)
            required_keys = ["otp", "login"]
            check_required_data = check_params(data, required_keys)
            if check_required_data:
                return make_json_response(422, check_required_data)

            USER_FIELDS_READ = [
                "title",
                "name",
                "phone",
                "email",
                "birthdate",
                "street",
                "street2",
                "image_1920",
                "country_id",
                "city",
                "otp",
                "login",
            ]

            # Validate fields
            unknown_keys = [key for key in data if key not in USER_FIELDS_READ]
            if unknown_keys:
                return make_json_response(422, {"message": f"الحقول غير معروفة: {', '.join(unknown_keys)}"})

            user = request.env["res.users"].sudo().search(
                [("login", "=", data.get("login"))])
            otp = data.pop("otp")

            if otp != user.last_otp:
                return make_json_response(400, {"message": "رمز التحقق غير صحيح."})

            # Handle optional image field
            if "image_1920" in data and not data.get("image_1920"):
                data.pop("image_1920")
            new_phone = data.get("phone")
            if new_phone and new_phone != user.phone:
                data["login"] = new_phone
            # Apply profile updates
            user.write(data)
            return make_json_response(200, {"message": "تم تعديل البيانات بنجاح."})

        except Exception as e:
            return make_json_response(422, {"message": str(e)})

    @http.route(
        "/v1/regenerate/otp/profile", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*"
    )
    @authorization_required
    def regenerate_otp_profile(self):
        try:
            user = request.env["res.users"].sudo().browse(request.uid)
            now = datetime.now()
            deadline = now - timedelta(minutes=2)
            timezone = pytz.timezone(user.tz or "UTC")
            if not user.login_sms_date or user.login_sms_date < deadline:
                otp = generateOTP()

                if user.phone:
                    send_sms(user.phone, f"رمز التحقق الخاص بك هو: {otp}")
                if user.email:
                    request.env["mail.mail"].sudo().create(
                        {
                            # "email_from": "no-reply@autochapeau.com",
                            "email_to": user.email,
                            "subject": "رمز التحقق",
                            "body_html": f"<p>رمز التحقق الخاص بك هو: {otp}</p>",
                        }
                    ).send()

                user.write(
                    {
                        "last_otp": otp,
                        "login_sms_date": now,
                    }
                )

                return make_json_response(200, {"message": "تم إعادة إرسال رمز التحقق.", "time_left": 120})
            else:
                message = (
                    "إذا لم تتلقى كود التحقق يمكنك المحاولة مرة أخرى بعد الساعة {}"
                ).format(
                    (
                        user.login_sms_date.astimezone(timezone)
                        + timedelta(minutes=2)
                    ).strftime("%H:%M:%S")
                )
                return make_json_response(401, {"message": message})

        except Exception as e:
            return make_json_response(500, {"message": str(e)})

    @http.route("/v1/my/vehicles", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    @with_lang
    def v1_get_my_vehicles(self):
        try:
            use_arabic = request.env.context.get(
                "lang", "en_US").startswith("ar")
            fields_name = [
                "id",
                "title",
                "model_id",
                "vin_sn",
                "size",
                "plate_letters",
                "plate_numbers",
                "license_plate",
                "category_id",
                "image_128",
            ]
            read_fields = fields_name + \
                (["plate_letters_ar", "plate_numbers_ar"] if use_arabic else [])
            brand_id = request.env.ref(
                "cars_management.unknown_manufacturer").id
            vehicles = (
                request.env["fleet.vehicle"]
                .sudo()
                .search_read(
                    [("brand_id", "!=", brand_id),
                     ("partner_id", "=", request.env.user.partner_id.id)],
                    read_fields,
                    order="title",
                )
            )
            if use_arabic:
                [
                    vehicle.update(
                        {
                            "plate_letters": vehicle.get("plate_letters_ar"),
                            "plate_numbers": vehicle.get("plate_numbers_ar"),
                        }
                    )
                    or vehicle.pop("plate_letters_ar", None)
                    or vehicle.pop("plate_numbers_ar", None)
                    for vehicle in vehicles
                ]

            result = format_search_read_result(
                vehicles, fields_name, [], model_name="fleet.vehicle")
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})

    @http.route("/v1/my/orders", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    @with_lang
    def v1_get_my_orders(self):
        result = []
        orders = (
            request.env["sale.order"]
            .sudo()
            .search([("state", "in", ("sale", "done")), ("partner_id", "=", request.env.user.partner_id.id)])
        )
        for order in orders:
            lines = []
            contain_service = bool(order.order_line.filtered(
                lambda line: line.product_id.detailed_type == "service"))
            for line in order.order_line:
                lines.append(
                    {
                        "id": line.id,
                        "name": line.name,
                        "product_uom_qty": line.product_uom_qty,
                        "price_unit": line.price_unit,
                        "price_subtotal": line.price_subtotal,
                        "is_service": line.product_id.detailed_type == "service",
                    }
                )
            transactions = []
            for transaction in order.transaction_ids:
                transactions.append(
                    {
                        "payment_method_id": transaction.payment_method_id.name,
                        "amount": (float(order.amount_total) + float(order.donation_amount))
                        - float(transaction.wallet_amount or 0.0),
                    }
                )
                if transaction.wallet_amount and transaction.wallet_amount != 0:
                    transactions.append(
                        {"payment_method_id": "Wallet", "amount": transaction.wallet_amount})

            result.append(
                {
                    "id": order.id,
                    "name": order.name,
                    "date_order": convert_utc_to_timezone(order.date_order),
                    "order_state": order.order_state,
                    "amount_total": float(order.amount_total) + float(order.donation_amount),
                    "company_id": order.company_id.name,
                    "vehicle_id": order.vehicle_id and order.vehicle_id.display_name or False,
                    "appointment_slot_id": order.appointment_slot_id
                    and str(order.appointment_slot_id.start_date)
                    or False,
                    "order_line": lines,
                    "transaction_ids": transactions,
                    "branch_id": order.branch_id.name
                    or (order.appointment_id and order.appointment_id.branch_id.name)
                    or False,
                    "contain_service": contain_service,
                    "access_token": order.access_token,
                }
            )
        return make_response(200, result)

    @http.route("/v1/my/invoices", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    def v1_get_my_invoices(self):
        fields_name = [
            "id",
            "name",
            "invoice_date",
            "amount_total",
            "company_id",
            "vehicle_id",
            "invoice_line_ids",
            "invoice_origin",
            "payment_ids",
            "access_token",
        ]
        line_fields_name = ["id", "name", "quantity",
                            "tax_ids", "discount", "price_unit", "price_subtotal", "product_id"]
        tax_fields_name = ["id", "amount"]
        payment_fields = ["id", "payment_method_id", "amount"]
        in_env = request.env["account.move"]
        inl_env = request.env["account.move.line"]
        tax_env = request.env["account.tax"]
        p_env = request.env["account.payment"]
        so_env = request.env["sale.order"]
        product_env = request.env["product.product"]
        invoices = in_env.sudo().search_read(
            [
                ("partner_id", "=", request.env.user.partner_id.id),
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "=", "posted"),
            ],
            fields_name,
        )
        for invoice in invoices:
            products = inl_env.sudo().search_read(
                [("id", "in", invoice.pop("invoice_line_ids"))], line_fields_name)
            for line in products:
                line["tax_ids"] = (
                    tax_env.sudo().search_read(
                        [("id", "in", line["tax_ids"])], tax_fields_name)
                    if line.get("tax_ids")
                    else []
                )
                product = product_env.sudo().browse(
                    line["product_id"][0]) if line.get("product_id") else False
                line["is_service"] = product.detailed_type == "service" if product else False
            invoice["invoice_line_ids"] = products
            payments = p_env.sudo().search_read(
                [("partner_id", "=", request.env.user.partner_id.id),
                 ("ref", "=", invoice["name"])],
                payment_fields,
                limit=1,
            )
            invoice["payment_ids"] = payments if payments else []
            donation = so_env.sudo().search_read(
                [("name", "=", invoice.get("invoice_origin"))], ["donation_amount", "branch_id", "vehicle_id"], limit=1
            )
            invoice["donation_amount"] = donation[0]["donation_amount"] if donation else 0.0
            invoice["branch_id"] = donation[0]["branch_id"][1] if donation and donation[0].get(
                "branch_id") else False
            # return vehicle_id field from the related Sale Order
            if not invoice.get("vehicle_id") or invoice["vehicle_id"] is False:
                invoice["vehicle_id"] = donation[0]["vehicle_id"][1] if donation and donation[0].get(
                    "vehicle_id") else False
        result = format_search_read_result(
            invoices, fields_name + ["donation_amount", "branch_id", "vehicle_id"], [])
        return make_response(200, result)

    @http.route("/v1/my/loyalty/history", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    def v1_get_loyalty_history(self):
        partner = request.env.user.partner_id
        orders = request.env["sale.order"].sudo().search(
            [("partner_id", "=", partner.id)])
        history = []
        for order in orders:
            if order.coupon_point_ids:
                gain_list = [
                    {
                        "date": order.date_order.strftime(DEFAULT_DATETIME_FORMAT),
                        "origin": order.name,
                        "type": "gain",
                        "points": line.points,
                    }
                    for line in order.coupon_point_ids
                    if line.points
                ]
                history.extend(gain_list)
        log_types = dict(
            partner.loyalty_exchange_log_ids._fields["type"].selection)
        for log in partner.loyalty_exchange_log_ids:
            if log.type == "loyalty_exchange":
                history.append(
                    {
                        "date": log.create_date.strftime(DEFAULT_DATETIME_FORMAT),
                        "origin": log_types.get(log.type),
                        "type": "loss",
                        "points": -log.points,
                    }
                )
        sorted_history = sorted(
            history, key=lambda item: datetime.strptime(item.get("date"), DEFAULT_DATETIME_FORMAT), reverse=True
        )
        return make_response(200, sorted_history)

    @http.route("/v1/my/wallet/history", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    def v1_get_wallet_history(self):
        partner = request.env.user.partner_id
        history = []
        log_types = dict(
            partner.loyalty_exchange_log_ids._fields["type"].selection)
        for log in partner.loyalty_exchange_log_ids:
            if log.type == "payment_by_wallet":
                history.append(
                    {
                        "date": log.create_date.strftime(DEFAULT_DATETIME_FORMAT),
                        "origin": log.order_id.name if log.order_id else False,
                        "type": "loss",
                        "points": -log.points,
                        "amount": -log.amount,
                    }
                )
            else:
                history.append(
                    {
                        "date": log.create_date.strftime(DEFAULT_DATETIME_FORMAT),
                        "origin": log_types.get(log.type),
                        "type": "gain",
                        "points": log.points,
                        "amount": log.amount,
                    }
                )
        sorted_history = sorted(
            history, key=lambda item: datetime.strptime(item.get("date"), DEFAULT_DATETIME_FORMAT), reverse=True
        )
        return make_response(200, sorted_history)
