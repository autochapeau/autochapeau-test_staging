import binascii

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.mail import _message_post_helper
from odoo.addons.portal.controllers.portal import CustomerPortal


class CheckinPortal(CustomerPortal):
    @http.route(["/my/checkin/<int:checkin_id>"], type="http", auth="public", website=True)
    def portal_my_checkin(self, checkin_id, report_type=None, access_token=None, message=False, download=False, **kw):
        try:
            checkin_sudo = self._document_check_access("car.checkin", checkin_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")

        if report_type in ("pdf", "html", "text"):
            return self._show_checkin_report(checkin_sudo, report_type, download=kw.get("download"))
        backend_url = f"/web#model={checkin_sudo._name}" f"&id={checkin_sudo.id}" f"&view_type=form"
        values = {
            "checkin": checkin_sudo,
            "message": message,
            "report_type": "html",
            "backend_url": backend_url,
            "res_company": checkin_sudo.company_id,
        }
        return request.render("cars_management.portal_my_checkin", values)

    @http.route(
        ["/my/checkin/<int:checkin_id>/accept"],
        type="json",
        auth="public",
        website=True,
    )
    def checkin_sign_accept(self, checkin_id, name=None, signature=None):
        # get from query string if not on json param
        checkin = request.env["car.checkin"].browse(int(checkin_id))
        if not signature:
            return {"error": _("Signature is missing.")}

        try:
            checkin.write(
                {
                    "signed_by": name,
                    "signed_on": fields.Datetime.now(),
                    "signature": signature,
                }
            )
            request.env.cr.commit()
        except (TypeError, binascii.Error):
            return {"error": _("Invalid signature data.")}

        _message_post_helper(
            "car.checkin",
            checkin.id,
            _("Checkin signed by %s", name),
        )
        query_string = "&message=sign_ok"
        return {
            "force_refresh": True,
            "redirect_url": checkin.get_portal_url(query_string=query_string),
        }

    @http.route(["/my/checkin/<int:checkin_id>/decline"], type="http", auth="public", methods=["POST"], website=True)
    def portal_checkin_decline(self, checkin_id, access_token=None, decline_message=None, **kwargs):
        try:
            checkin_sudo = self._document_check_access("car.checkin", checkin_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")

        if checkin_sudo._has_to_be_signed() and decline_message:
            checkin_sudo.action_cancel()
            _message_post_helper(
                "car.checkin",
                checkin_sudo.id,
                decline_message,
                token=access_token,
            )
            redirect_url = checkin_sudo.get_portal_url()
        else:
            redirect_url = checkin_sudo.get_portal_url(query_string="&message=cant_reject")

        return request.redirect(redirect_url)
