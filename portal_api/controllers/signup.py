import json
import math
import random
from datetime import datetime, timedelta

import pytz

from odoo import SUPERUSER_ID, http
from odoo.http import request

from .common import check_params, check_request_body, make_json_response
from .sms import send_sms


def generateOTP():
    """Generate One time password"""
    digits = "0123456789"
    OTP = ""
    for _i in range(4):
        OTP += digits[math.floor(random.random() * 10)]
    return OTP


class SignupApi(http.Controller):
    @http.route("/v1/send/otp", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @check_request_body
    def v1_api_send_otp(self):
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["mobile", "code"])
        if check_data:
            return make_json_response(422, check_data)

        try:
            code = data.get("code")
            mobile = data.get("mobile")
            full_number = f"+{code}{mobile}"
            user = request.env["res.users"].sudo().search(
                [("login", "=", mobile)], limit=1)
            if user:
                return make_json_response(
                    409, {
                        "message": "تم التسجيل مسبقاً برقم الجوال المدخل. يرجى استخدام رقم جوال آخر."}
                )
            otp = generateOTP()
            now = datetime.now()

            sms_message = f"رمز التحقق الخاص بك هو: {otp}"
            send_sms(full_number, sms_message)
            time_left = int((now + timedelta(minutes=2) - now).total_seconds())
            # Store OTP for unregistered users
            request.env["ir.config_parameter"].sudo().set_param(
                f"register_{mobile}_otp", otp)

            return make_json_response(
                200, {"time_left": time_left,
                      "message": "تم إرسال رمز التحقق إلى هاتفك."}
            )

        except Exception as e:
            return make_json_response(500, {"message": str(e)})

    @http.route("/v1/signup", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @check_request_body
    def v1_api_signup(self):
        data = json.loads(request.httprequest.data)
        check_data = check_params(
            data, ["login", "otp", "password", "name", "code"])
        if check_data:
            return make_json_response(422, check_data)
        login = data.get("login")
        otp = data.get("otp")
        otp_stored = request.env["ir.config_parameter"].sudo(
        ).get_param(f"register_{login}_otp")
        country = request.env["res.country"].sudo().search(
            [("phone_code", "=", data.get("code"))], limit=1)
        try:
            if login and otp and otp_stored and otp_stored == otp:
                companies = request.env["res.company"].sudo().search([])
                portal_group = request.env.ref(
                    "base.group_portal", raise_if_not_found=False)

                values = {
                    "name": data.get("name"),
                    "login": login,
                    "password": data.get("password"),
                    "phone": login,
                    "customer_rank": 1,
                    "last_otp": data.get("otp"),
                    "login_sms_date": datetime.now(),
                    "groups_id": [(6, 0, [portal_group.id])] if portal_group else [],
                    "company_id": companies[0].id if companies else False,
                    "company_ids": [(6, 0, companies.ids)] if companies else [],
                }
                user = (
                    request.env["res.users"]
                    .with_user(SUPERUSER_ID)
                    .with_company(values.get("company_id"))
                    .create(values)
                )
                # Commit the transaction before authentication
                request.env.cr.commit()

                # Authenticate the user session
                request.session.authenticate(
                    request.env.cr.dbname, login, data.get("password"))
                api_keys_obj = request.env["res.users.apikeys"].sudo()
                # Generate API Key
                key = api_keys_obj._generate("api", "api mobile app")
                # Clear temporary stored values
                request.env["ir.config_parameter"].sudo().set_param(
                    f"register_{login}_otp", False)

                # Initialize the wallet balance to 0
                user = request.env["res.users"].sudo().search(
                    [("login", "=", login)], limit=1)
                if country:
                    user.sudo().partner_id.sudo().write(
                        {"country_id": country.id})
                program_ewallet = (
                    request.env["loyalty.program"].sudo().search(
                        [("program_type", "=", "ewallet")], limit=1)
                )
                program_loyalty = (
                    request.env["loyalty.program"].sudo().search(
                        [("program_type", "=", "loyalty")], limit=1)
                )

                cards = user.partner_id.loyalty_card_ids.filtered(
                    lambda card: not card.program_id)

                if program_ewallet and program_loyalty and len(cards) >= 2:
                    cards[0].sudo().write(
                        {
                            "program_id": program_ewallet.id,
                            "points": 0,
                        }
                    )
                    cards[1].sudo().write(
                        {
                            "program_id": program_loyalty.id,
                            "points": 0,
                        }
                    )

                return make_json_response(
                    200,
                    {
                        "message": "مرحباً بك! تم التحقق من رقمك بنجاح.",
                        "api_key": key,
                        "user_id": user.id,
                    },
                )

            return make_json_response(401, {"message": "رمز التحقق غير صالح."})

        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(500, {"message": str(e)})

    @http.route(
        "/v1/regenerate/otp",
        type="json",
        auth="none",
        csrf=False,
        methods=["POST", "OPTIONS"],
        cors="*",
    )
    def v1_regenerate_otp(self):
        data = json.loads(request.httprequest.data)
        check_required_data = check_params(data, ["mobile"])
        if check_required_data:
            return make_json_response(422, check_required_data)
        try:
            # Generate a new OTP
            new_otp = generateOTP()
            # Send SMS only if a valid phone number is present
            if data.get("mobile"):
                deadline = datetime.now() - timedelta(minutes=2)
                user = request.env["res.users"].sudo().search(
                    [("login", "=", data.get("mobile"))], limit=1)
                timezone = pytz.timezone(user.tz or "UTC")
                if not user.login_sms_date or user.login_sms_date < deadline:
                    now = datetime.now(timezone)
                    user.sudo().write(
                        {"login_sms_date": datetime.now(), "last_otp": new_otp})
                    message_template = "رمز التحقق الجديد الخاص بك هو: {}"
                    send_sms(data.get("mobile"),
                             message_template.format(new_otp))
                    time_left = int(
                        (now + timedelta(minutes=2) - now).total_seconds())
                    return make_json_response(
                        200, {"message": "تم تجديد رمز التحقق بنجاح",
                              "time_left": time_left}
                    )
                else:
                    # Check OTP resend delay (2 minutes)

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
            return make_json_response(422, {"message": str(e)})
