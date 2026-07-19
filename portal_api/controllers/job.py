import json

from odoo import SUPERUSER_ID, http
from odoo.http import request

from .common import check_params, create_attachments, format_search_read_result, make_json_response, make_response


class JobAPI(http.Controller):
    @http.route("/v1/jobs", type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], cors="*")
    def v1_get_jobs(self):
        fields_name = ["id", "name", "department_id", "no_of_recruitment", "description"]
        jobs = request.env["hr.job"].sudo().search_read([], fields_name)
        result = format_search_read_result(jobs, fields_name, [])
        return make_response(200, result)

    @http.route("/v1/jobs", type="json", auth="none", csrf=False, methods=["POST", "OPTIONS"], cors="*")
    def v1_create_jobs(self):
        data = json.loads(request.httprequest.data)
        required_keys = ["partner_name", "email_from", "partner_mobile", "description", "job_id"]
        check_required_data = check_params(data, required_keys)
        if check_required_data:
            return make_json_response(422, check_required_data)
        data.update({"name": data.get("partner_name")})
        try:
            # Attachments
            attachment_ids = []
            if data.get("attachment_ids"):
                attachment_ids = create_attachments(data.get("attachment_ids"))
                data.pop("attachment_ids")
            # create applicant
            applicant = request.env["hr.applicant"].with_user(SUPERUSER_ID).create(data)
            # update Attachments
            if attachment_ids:
                request.env["ir.attachment"].sudo().browse(attachment_ids).write(
                    {"res_id": applicant.id, "res_model": "hr.applicant"}
                )
        except Exception as e:
            request.env.cr.rollback()
            return make_json_response(422, {"message": str(e)})
        response_data = {"message": "success", "applicant_id": applicant.id}
        return make_json_response(200, response_data)
