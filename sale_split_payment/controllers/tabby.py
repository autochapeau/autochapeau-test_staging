import html

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request


class SaleSplitPaymentTabbyController(http.Controller):
    @http.route(
        "/sale_split_payment/tabby/return/<string:access_token>",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET"],
    )
    def tabby_return(self, access_token, result=None, **kwargs):
        allocation = (
            request.env["sale.order.payment"]
            .sudo()
            .search([("access_token", "=", access_token)], limit=1)
        )
        if not allocation:
            return request.not_found()

        if result == "success":
            try:
                allocation._refresh_tabby_status()
            except UserError as error:
                allocation.write(
                    {
                        "state": "pending",
                        "error_message": str(error),
                    }
                )
        elif result in ("cancel", "failure") and allocation.state != "paid":
            allocation.write(
                {
                    "state": "failed",
                    "provider_status": result,
                    "error_message": _(
                        "The Tabby checkout was cancelled or failed."
                    ),
                }
            )

        if allocation.state == "paid":
            title = _("Payment approved")
            message = _("Your payment was received successfully.")
        elif allocation.state == "pending":
            title = _("Payment pending")
            message = _(
                "Tabby has not confirmed the payment yet. The status can be refreshed from the sale order."
            )
        else:
            title = _("Payment not completed")
            message = allocation.error_message or _(
                "The payment was not approved."
            )

        body = """
            <!doctype html>
            <html lang="en">
              <head><meta charset="utf-8"><title>%s</title></head>
              <body style="font-family: sans-serif; margin: 3rem">
                <h2>%s</h2>
                <p>%s</p>
                <p>%s: %s</p>
              </body>
            </html>
        """ % (
            html.escape(str(title)),
            html.escape(str(title)),
            html.escape(str(message)),
            html.escape(str(_("Reference"))),
            html.escape(allocation.name),
        )
        return request.make_response(
            body,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
