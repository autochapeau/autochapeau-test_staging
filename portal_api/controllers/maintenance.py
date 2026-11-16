import json

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from .common import authorization_required, make_response, with_lang


def _owned_order(order_id):
    # Never look up a claim or service from a client-supplied ID before ownership.
    return request.env["sale.order"].sudo().search([
        ("id", "=", order_id), ("partner_id", "=", request.env.user.partner_id.id),
        ("state", "in", ["sale", "done"]),
    ], limit=1)


def _source_tasks(order):
    return request.env["car.workorder.service"].sudo().search([
        ("product_id", "in", order.order_line.product_id.ids),
        ("workorder_id.company_id", "=", order.company_id.id),
        ("materials_issued", "=", True),
        "|", ("workorder_id.sale_order_id", "=", order.id),
        ("workorder_id.appointment_id.sale_order_id", "=", order.id),
    ])


def _issued_parts(task):
    return task.workorder_id.product_ids.filtered(
        lambda row: row.source_task_id == task and row.part_id
        and row.material_move_id.state == "done" and row.quantity > 0
    ).mapped("part_id")


class WebsiteMaintenance(http.Controller):
    @http.route("/v1/my/orders/<int:order_id>/maintenance", type="http", auth="none",
                csrf=False, methods=["GET", "POST", "OPTIONS"], cors="*")
    @authorization_required
    @with_lang
    def maintenance(self, order_id):
        order = _owned_order(order_id)
        if not order:
            return make_response(404, "Order not found.")
        tasks = _source_tasks(order)
        if request.httprequest.method == "POST":
            try:
                data = json.loads(request.httprequest.data or b"{}")
                if not isinstance(data, dict):
                    return make_response(422, "Invalid request body.")
                line = order.order_line.filtered(lambda row: row.id == int(data.get("service_line_id", 0)))
                task = tasks.filtered(lambda row: row.id == int(data.get("source_task_id", 0)))
                if len(line) != 1 or len(task) != 1 or task.product_id != line.product_id:
                    return make_response(422, "Select an issued service belonging to this order.")
                requested_parts = {int(part_id) for part_id in data.get("part_ids", [])}
                allowed_parts = _issued_parts(task)
                if not requested_parts or not requested_parts.issubset(set(allowed_parts.ids)):
                    return make_response(422, "Select parts from this service's original delivery.")
                description = str(data.get("description") or "").strip()
                if not description or len(description) > 4000:
                    return make_response(422, "Describe the issue using 1 to 4000 characters.")
                claims = request.env["maintenance.claim"].sudo()
                request.env.cr.execute("SELECT pg_advisory_xact_lock(802063, %s)", [task.id])
                if claims.search_count([("origin_sale_id", "=", order.id),
                                        ("source_task_id", "=", task.id), ("state", "=", "quality")]):
                    return make_response(409, "This service already has a maintenance request awaiting review.")
                with request.env.cr.savepoint():
                    wizard = request.env["maintenance.claim.wizard"].sudo().create({
                        "sale_order_id": order.id, "service_line_id": line.id,
                        "source_task_id": task.id, "selected_part_ids": [(6, 0, sorted(requested_parts))],
                        "problem_location": description,
                    })
                    action = wizard.action_confirm()
                    claim = claims.browse(action["res_id"])
                    claim.write({"website_request_user_id": request.env.user.id})
                return make_response(201, {"id": claim.id, "name": claim.name, "state": claim.state})
            except (ValueError, TypeError, UserError, ValidationError) as error:
                return make_response(422, {"message": str(error)})
        services = []
        for line in order.order_line.filtered(lambda row: not row.display_type and row.product_id.detailed_type == "service"):
            for task in tasks.filtered(lambda row: row.product_id == line.product_id):
                parts = _issued_parts(task)
                if parts:
                    services.append({
                        "service_line_id": line.id, "source_task_id": task.id,
                        "name": line.product_id.display_name, "warranty": line.product_id.warranty or False,
                        "work_order": task.workorder_id.name,
                        "completed_at": str(task.date_end) if task.date_end else False,
                        "parts": [{"id": part.id, "name": part.name} for part in parts],
                    })
        history = request.env["maintenance.claim"].sudo().search([("origin_sale_id", "=", order.id)])
        return make_response(200, {
            "order": order.name, "vehicle": order.vehicle_id.display_name, "services": services,
            "history": [{"id": claim.id, "name": claim.name, "state": claim.state,
                         "service": claim.service_product_id.display_name,
                         "description": claim.problem_location, "date": str(claim.create_date),
                         "appointment": str(claim.appointment_id.start_date) if claim.appointment_id and claim.appointment_id.start_date else False}
                        for claim in history],
        })
