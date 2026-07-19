import json
from datetime import datetime, timedelta

import pytz

from odoo import http
from odoo.http import request

from odoo.addons.auth_signup.models.res_partner import now

from .common import check_params, check_request_body, make_json_response
from .signup import generateOTP
from .sms import send_sms


class ResetPassword(http.Controller):
    @http.route("/v1/reset_password", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    @check_request_body
    def v1_reset_password(self):
        """This endpoint is used to reset users passwords."""
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["login"])
        if check_data:
            return make_json_response(422, check_data)
        login = data.get("login")
        try:
            user = request.env["res.users"].sudo()
            deadline = datetime.now() - timedelta(minutes=2)
            otp = generateOTP()
            domain = [("email", "=", login)] if "@" in login else [("phone", "=", login)]
            user = user.search(domain, limit=1)
            # Check if user and phone exist
            if not user or not user.phone:
                return make_json_response(404, "User not found or phone missing.")

            timezone = pytz.timezone(user.tz or "UTC")
            now = datetime.now(timezone)
            # Prevent OTP resend within 2 minutes
            if user.login_sms_date and user.login_sms_date > deadline:
                retry_time = (user.login_sms_date.astimezone(timezone) + timedelta(minutes=2)).strftime("%H:%M:%S")
                time_left = int((user.login_sms_date.astimezone(timezone) + timedelta(minutes=2) - now).total_seconds())
                message = f"If you did not receive the code, you can try again after {retry_time}"
                return make_json_response(401, {"message": message, "time_left": time_left, "phone": user.phone})

            # Save OTP and current time
            user.sudo().write({"login_sms_date": datetime.now(), "last_otp": otp})
            time_left = int((now + timedelta(minutes=2) - now).total_seconds())
            send_sms(login, send_sms(user.phone, f"Your OTP code is: {otp}"))
            return make_json_response(
                200,
                {
                    "phone": user.phone,
                    "time_left": time_left,
                    "message": "OTP sent via SMS.",
                },
            )

        except Exception as e:
            return make_json_response(500, {"message": str(e)})

    @http.route(
        "/v1/reset_password/verify/otp", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*"
    )
    @check_request_body
    def v1_reset_password_verify_otp(self):
        """Verify the OTP code sent for password reset."""
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["login", "otp"])
        if check_data:
            return make_json_response(422, check_data)

        login = data.get("login")
        otp = data.get("otp")

        try:
            user = request.env["res.users"].sudo()
            domain = [("email", "=", login)] if "@" in login else [("phone", "=", login)]
            user = user.search(domain, limit=1)

            if not user:
                return make_json_response(404, {"message": "المستخدم غير موجود."})

            if user.last_otp != otp:
                return make_json_response(401, {"message": "رمز التحقق غير صالح."})
            expiration = now(days=+1)
            user.partner_id.signup_prepare(signup_type="reset", expiration=expiration)
            signup_token = user.partner_id.signup_token

            return make_json_response(
                200, {"token": signup_token, "message": "رمز التحقق صالح. يمكنك الآن إعادة تعيين كلمة المرور."}
            )

        except Exception as e:
            return make_json_response(500, {"message": str(e)})

    @http.route(
        "/v1/reset_password/validate", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*"
    )
    @check_request_body
    def v1_reset_password_validation(self):
        """This endpoint is used to validate passwords."""
        data = json.loads(request.httprequest.data)
        check_data = check_params(data, ["token", "password"])
        if check_data:
            return make_json_response(422, check_data)
        try:
            token = data.pop("token")
            request.env["res.users"].sudo().signup(data, token)
            return make_json_response(200, "Password was reset successfully")
        except Exception as e:
            return make_json_response(500, {"message": e})
