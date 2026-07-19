import binascii

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.portal.controllers.mail import _message_post_helper
from odoo.addons.portal.controllers.portal import CustomerPortal


class checkoutPortal(CustomerPortal):
    @http.route(["/my/checkout/<int:checkout_id>"], type="http", auth="public", website=True)
    def portal_my_checkout(self, checkout_id, report_type=None, access_token=None, message=False, download=False, **kw):
        try:
            checkout_sudo = self._document_check_access(
                "car.checkout", checkout_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")

        if report_type in ("pdf", "html", "text"):
            return self._show_checkout_report(checkout_sudo, report_type, download=kw.get("download"))
        backend_url = f"/web#model={checkout_sudo._name}" f"&id={checkout_sudo.id}" f"&view_type=form"
        values = {
            "checkout": checkout_sudo,
            "message": message,
            "report_type": "html",
            "backend_url": backend_url,
            "res_company": checkout_sudo.company_id,
        }
        return request.render("cars_management.portal_my_checkout", values)

    @http.route(
        ["/my/checkout/<int:checkout_id>/accept"],
        type="json",
        auth="public",
        website=True,
    )
    def checkout_sign_accept(self, checkout_id, name=None, signature=None):
        # get from query string if not on json param
        checkout = request.env["car.checkout"].browse(int(checkout_id))
        if not signature:
            return {"error": _("Signature is missing.")}

        try:
            checkout.write(
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
            "car.checkout",
            checkout.id,
            _("Checkout signed by %s", name),
        )

        # Automatically create invoice from the linked sale order
        checkout._create_invoice_from_sale_order()

        query_string = "&message=sign_ok"
        return {
            "force_refresh": True,
            "redirect_url": checkout.get_portal_url(query_string=query_string),
        }

    @http.route(["/my/checkout/<int:checkout_id>/decline"], type="http", auth="public", methods=["POST"], website=True)
    def portal_checkout_decline(self, checkout_id, access_token=None, decline_message=None, **kwargs):
        try:
            checkout_sudo = self._document_check_access(
                "car.checkout", checkout_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")

        if checkout_sudo._has_to_be_signed() and decline_message:
            checkout_sudo.action_cancel()
            _message_post_helper(
                "car.checkout",
                checkout_sudo.id,
                decline_message,
                token=access_token,
            )
            redirect_url = checkout_sudo.get_portal_url()
        else:
            redirect_url = checkout_sudo.get_portal_url(
                query_string="&message=cant_reject")

        return request.redirect(redirect_url)
