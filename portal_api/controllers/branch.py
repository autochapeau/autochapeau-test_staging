from odoo import http
from odoo.http import request

from .common import authorization_required, make_response, with_lang


class BranchAPI(http.Controller):
    @http.route("/v1/branches", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    @authorization_required
    @with_lang
    def v1_get_branches(self):
        try:
            fields_name = ["id", "name", "code", "company_id"]
            branches = request.env["hr.department"].sudo().search_read(
                [("department_type", "=", "branche"), ("company_id", "!=", False)],
                fields_name
            )
            result = [
                {
                    "id": b["id"],
                    "name": b["name"],
                    "code": b["code"],
                    "company_id": b["company_id"][0] if b.get("company_id") else False,
                }
                for b in branches
            ]
            return make_response(200, result)
        except Exception as e:
            return make_response(422, {"message": str(e)})
