from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .material_execution import _ISSUE_TOKEN


_MANAGER = "work_orders.group_workshop_manager"
_PREPARER = "workorder_service_components.group_workshop_material_preparer"
_PREPARATION_EDIT = object()
_TASK_TRANSITION = object()
_EDITABLE_MATERIAL = {"product_id", "material_brand_id", "actual_length_in", "actual_width_in", "quantity", "lot_id"}


class Appointment(models.Model):
    _inherit = "car.appointment"

    def _work_order_service_materials(self, service):
        # The work order builds part requirements without selecting a stock product.
        return []


class Warehouse(models.Model):
    _inherit = "stock.warehouse"

    workshop_preparer_id = fields.Many2one(
        "res.users", string="Workshop Materials Preparer",
        domain=lambda self: [("groups_id", "in", self.env.ref(_PREPARER).ids)],
        help="المستخدم ده هيتعيّن تلقائي على طلبات تجهيز الخامات الجديدة لفرع المستودع.",
    )
    workshop_stock_warning_only = fields.Boolean(
        string="Allow Workshop Start Before Stock Count",
        groups="stock.group_stock_manager",
        help="لحد ما الجرد يخلص، نقص الرصيد يظهر تنبيه وقت تجهيز الخامات وبدء الشغل. صرف الخامات لسه بيتحقق من الرصيد.",
    )


class WorkOrder(models.Model):
    _inherit = "car.work.order"

    material_preparation_enabled = fields.Boolean(readonly=True, copy=False)
    material_preparation_ids = fields.One2many(
        "car.workshop.preparation", "workorder_id", string="Material Preparation", copy=False,
        groups=_MANAGER,
    )
    material_preparation_ready = fields.Boolean(compute="_compute_preparation_status", compute_sudo=True)
    material_preparation_count = fields.Integer(compute="_compute_preparation_status", compute_sudo=True)

    @api.depends("material_preparation_ids.state")
    def _compute_preparation_status(self):
        for order in self:
            requests = order.material_preparation_ids
            order.material_preparation_count = len(requests)
            order.material_preparation_ready = all(request.state == "prepared" for request in requests)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("appointment_id") and not vals.get("parent_id") and vals.get("state", "new") == "new":
                vals["material_preparation_enabled"] = True
        return super().create(vals_list)

    def _prepare_part_material_values(self, task, component):
        vals = super()._prepare_part_material_values(task, component)
        if self.material_preparation_enabled or self._can_adopt_legacy_preparation():
            category = component.material_category_id or component.product_id.categ_id
            vals.update(product_id=False, material_brand_id=False, tag_id=False, quantity=0,
                        material_category_id=category.id)
        return vals

    def _lock_workshop_flow(self):
        self.flush_recordset()
        for order in self.sorted("id"):
            self.env.cr.execute("SELECT id FROM car_work_order WHERE id = %s FOR UPDATE", (order.id,))
        self.invalidate_recordset([
            "state", "material_preparation_enabled", "material_preparation_ids",
            "product_ids", "service_ids", "picking_id", "material_picking_ids",
        ])

    def _check_workshop_manager(self):
        if not (self.env.su or self.env.user.has_group(_MANAGER)):
            raise AccessError(_("A workshop manager must perform this action."))
        self.check_access_rights("write")
        self.check_access_rule("write")

    def _create_delivery_picking(self):
        if self.material_preparation_enabled and not self.product_ids.filtered(
            lambda line: line.product_id and not line.source_task_id and line.quantity > 0
        ):
            return self.env["stock.picking"]
        return super()._create_delivery_picking()

    def _can_adopt_legacy_preparation(self):
        self.ensure_one()
        order = self.sudo()
        if (order.state != "new" or not order.appointment_id or order.parent_id
                or order.picking_id or order.material_picking_ids):
            return False
        if order.service_ids.filtered(
            lambda task: task.state not in ("waiting", "ready", "cancel")
            or task.date_start or task.materials_issued or task.material_picking_id
        ):
            return False
        # Existing part rows can be reused as saved. A service material without a
        # part cannot be matched automatically without risking a duplicate issue.
        return not order.product_ids.filtered(
            lambda line: line.material_move_id
            or ((line.service_id or line.source_task_id) and not line.source_component_id)
        )

    def action_confirm(self):
        self.ensure_one()
        if not (self.material_preparation_enabled or self._can_adopt_legacy_preparation()):
            return super().action_confirm()
        self._check_workshop_manager()
        self._lock_workshop_flow()
        if self.state != "new":
            raise UserError(_("Only a new work order can be confirmed."))
        if not (self.material_preparation_enabled or self._can_adopt_legacy_preparation()):
            return super().action_confirm()
        order = self.with_context(workshop_flow_transition=_PREPARATION_EDIT)
        with self.env.cr.savepoint():
            if not order.material_preparation_enabled:
                order.material_preparation_enabled = True
            return order._confirm_with_material_preparation()

    def _confirm_with_material_preparation(self):
        result = super().action_confirm()
        tasks = self.service_ids.filtered(lambda task: task.state != "cancel")
        if tasks.filtered(lambda task: not task.staff_ids):
            raise UserError(_("Assign at least one technician to every service before confirming."))
        material_lines = self.product_ids.filtered(lambda line: line.source_component_id and line.source_task_id in tasks)
        if material_lines:
            warehouse = self._get_branch_warehouse()
            requests = []
            for task, lines in material_lines.grouped("source_task_id").items():
                assignee = task.material_preparer_id or warehouse.workshop_preparer_id
                if assignee and (not assignee.active or not assignee.has_group(_PREPARER)
                                 or self.company_id not in assignee.company_ids):
                    raise UserError(_("The assigned materials preparer must have the preparation role and access to this company."))
                requests.append({
                    "workorder_id": self.id,
                    "task_id": task.id,
                    "service_id": task.product_id.id,
                    "company_id": self.company_id.id,
                    "user_id": assignee.id,
                    "line_ids": [fields.Command.create({"material_line_id": line.id}) for line in lines],
                })
            self.env["car.workshop.preparation"].sudo().create(requests)
        return result

    def action_view_material_preparation(self):
        self.ensure_one()
        self._check_workshop_manager()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "workorder_service_components.action_workshop_material_preparation")
        action["domain"] = [("id", "in", self.material_preparation_ids.ids)]
        return action

    def action_progress(self):
        self.ensure_one()
        if not self.material_preparation_enabled:
            return super().action_progress()
        self._check_workshop_manager()
        self._lock_workshop_flow()
        if self.state != "confirmed" or self.checkin_state != "done" or not self.material_preparation_ready:
            raise UserError(_("Confirm the order and complete material preparation before starting."))
        self.material_preparation_ids._check_stock()
        result = super(WorkOrder, self.with_context(workshop_flow_transition=_PREPARATION_EDIT)).action_progress()
        self.service_ids.filtered(lambda task: task.state == "waiting").with_context(
            workshop_task_transition=_TASK_TRANSITION
        ).state = "ready"
        return result

    def action_start_materials(self):
        self.ensure_one()
        if self.material_preparation_enabled and self.state == "confirmed":
            return self.action_progress()
        return super().action_start_materials()

    def action_cancel(self):
        deferred = self.filtered("material_preparation_enabled")
        if deferred:
            deferred._check_workshop_manager()
        return super(WorkOrder, self.with_context(workshop_flow_transition=_PREPARATION_EDIT)).action_cancel()

    def write(self, vals):
        if ("material_preparation_enabled" in vals and not self.env.su
                and self.env.context.get("workshop_flow_transition") is not _PREPARATION_EDIT):
            raise AccessError(_("Material preparation is determined by the workshop workflow."))
        if "state" in vals and not self.env.su and self.env.context.get("workshop_flow_transition") is not _PREPARATION_EDIT:
            changed = self.filtered(lambda order: order.material_preparation_enabled and order.state != vals["state"])
            if changed:
                if vals["state"] != "progress" or changed.filtered(lambda order: order.state != "quality"):
                    raise UserError(_("Use the workshop actions to advance this work order."))
                changed._check_workshop_manager()
        return super().write(vals)


class WorkOrderService(models.Model):
    _inherit = "car.workorder.service"

    material_preparer_id = fields.Many2one(
        "res.users", string="Materials Preparer", groups=_MANAGER,
        domain=lambda self: [("groups_id", "in", self.env.ref(_PREPARER).ids)],
        help="Optional override of the branch warehouse's default preparer.",
    )

    def _check_execution_actor(self):
        self.ensure_one()
        order = self.workorder_id.sudo()
        if not order.material_preparation_enabled:
            return
        self.check_access_rights("write")
        self.check_access_rule("write")
        if not (self.env.su or self.env.user.has_group(_MANAGER) or self.env.user in self.sudo().staff_ids.user_id):
            raise AccessError(_("Only an assigned technician or the workshop manager can execute this task."))
        order._lock_workshop_flow()
        self.invalidate_recordset(["state"])
        if order.state != "progress" or self.state not in ("waiting", "ready", "progress"):
            raise UserError(_("The workshop manager must start the prepared order before technicians can execute its tasks."))

    def action_start(self):
        self._check_execution_actor()
        return super(WorkOrderService, self.with_context(workshop_task_transition=_TASK_TRANSITION)).action_start()

    def action_break(self):
        self._check_execution_actor()
        return super(WorkOrderService, self.with_context(workshop_task_transition=_TASK_TRANSITION)).action_break()

    def action_confirm_pause(self, reason, reason_note=False):
        self._check_execution_actor()
        return super(WorkOrderService, self.with_context(workshop_task_transition=_TASK_TRANSITION)).action_confirm_pause(reason, reason_note)

    def action_finish(self):
        self._check_execution_actor()
        return super(WorkOrderService, self.with_context(workshop_task_transition=_TASK_TRANSITION)).action_finish()

    def write(self, vals):
        if (
            set(vals) & {"state", "date_start", "date_end", "pause_start", "pause_duration"}
            and not self.env.su and self.env.context.get("workshop_task_transition") is not _TASK_TRANSITION
            and self.sudo().workorder_id.filtered("material_preparation_enabled")
        ):
            raise AccessError(_("Use the task actions to change the workshop execution state."))
        return super().write(vals)


class WorkOrderProduct(models.Model):
    _inherit = "car.workorder.product"

    def write(self, vals):
        if (
            set(vals) & (_EDITABLE_MATERIAL | {"used_uom_id"})
            and self.env.context.get("workshop_preparation_edit") is not _PREPARATION_EDIT
            and self.env.context.get("material_issue_token") is not _ISSUE_TOKEN
            and self.filtered(lambda line: line.source_component_id and line.workorder_id.material_preparation_enabled)
        ):
            raise UserError(_("Edit the service material using its preparation request."))
        return super().write(vals)


class WorkshopPreparation(models.Model):
    _name = "car.workshop.preparation"
    _description = "Workshop Material Preparation"
    _rec_name = "service_id"
    _order = "id desc"

    workorder_id = fields.Many2one("car.work.order", required=True, ondelete="cascade", groups=_MANAGER)
    task_id = fields.Many2one("car.workorder.service", required=True, ondelete="cascade", groups=_MANAGER)
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    service_id = fields.Many2one("product.product", string="Service", required=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Materials Preparer", groups=_MANAGER,
                             domain=lambda self: [("groups_id", "in", self.env.ref(_PREPARER).ids)])
    state = fields.Selection([("pending", "To Prepare"), ("prepared", "Prepared")],
                             default="pending", required=True, readonly=True)
    line_ids = fields.One2many("car.workshop.preparation.line", "preparation_id", string="Parts")

    _sql_constraints = [("task_unique", "unique(task_id)", "A task can only have one preparation request.")]

    def _editable_request(self):
        self.ensure_one()
        self.check_access_rights("write")
        self.check_access_rule("write")
        request = self.sudo()
        request.workorder_id._lock_workshop_flow()
        request.invalidate_recordset(["user_id", "state", "line_ids"])
        self.check_access_rule("write")
        if request.workorder_id.state != "confirmed" or request.state != "pending":
            raise UserError(_("Only a pending request on a confirmed work order can be edited."))
        return request

    def write(self, vals):
        vals = dict(vals)
        if self.env.context.get("workshop_preparation_edit") is _PREPARATION_EDIT:
            return super().write(vals)
        permitted = {"line_ids"}
        if self.env.su or self.env.user.has_group(_MANAGER):
            permitted.add("user_id")
        if set(vals) - permitted:
            raise AccessError(_("Preparation status and assignments must use the workshop workflow."))
        for request in self:
            secured = request._editable_request()
            for command in vals.get("line_ids", []):
                if command[0] != fields.Command.UPDATE or command[1] not in secured.line_ids.ids:
                    raise AccessError(_("Only existing parts on this request can be edited."))
                request.line_ids.browse(command[1]).write(command[2])
            if "user_id" in vals:
                user = self.env["res.users"].sudo().browse(vals["user_id"]).exists()
                if user and (not user.active or not user.has_group(_PREPARER)
                             or secured.company_id not in user.company_ids):
                    raise UserError(_("Select an active materials preparer with access to this company."))
                super(WorkshopPreparation, request).write({"user_id": user.id})
        return True

    def _check_stock(self):
        lines = self.sudo().line_ids.material_line_id
        if lines.filtered(lambda line: not line.product_id):
            raise UserError(_("Choose the actual material for every part before completing preparation."))
        lines._check_actual_dimensions()
        if lines.filtered(lambda line: line.quantity > 0 and line.product_id.tracking != "none" and not line.lot_id):
            raise UserError(_("Select the lot or serial number for each tracked material."))
        lines.invalidate_recordset(["branch_available_qty", "material_stock_shortage", "material_stock_warning"])
        shortages = lines.filtered("material_stock_shortage").filtered(
            lambda line: not line.availability_warehouse_id.workshop_stock_warning_only
        )
        if shortages:
            raise UserError("\n".join(shortages.mapped("material_stock_warning")))

    def action_mark_prepared(self):
        for request in self:
            secured = request._editable_request()
            secured._check_stock()
            secured.with_context(workshop_preparation_edit=_PREPARATION_EDIT).state = "prepared"
        return True

    def action_reopen(self):
        self.ensure_one()
        if not (self.env.su or self.env.user.has_group(_MANAGER)):
            raise AccessError(_("Only a workshop manager can reopen a preparation request."))
        self.check_access_rule("write")
        order = self.sudo().workorder_id
        order._lock_workshop_flow()
        self.invalidate_recordset(["state"])
        if order.state != "confirmed" or self.state != "prepared":
            raise UserError(_("A request can only be reopened before workshop execution starts."))
        self.with_context(workshop_preparation_edit=_PREPARATION_EDIT).state = "pending"
        return True


class WorkshopPreparationLine(models.Model):
    _name = "car.workshop.preparation.line"
    _description = "Workshop Material Preparation Part"
    _rec_name = "part_id"

    preparation_id = fields.Many2one("car.workshop.preparation", required=True, ondelete="cascade")
    material_line_id = fields.Many2one("car.workorder.product", required=True, ondelete="cascade", groups=_MANAGER)
    part_id = fields.Many2one(related="material_line_id.part_id")
    material_category_id = fields.Many2one(related="material_line_id.material_category_id")
    allowed_brand_ids = fields.Many2many(related="material_line_id.allowed_brand_ids")
    material_brand_id = fields.Many2one(related="material_line_id.material_brand_id", readonly=False)
    product_id = fields.Many2one(related="material_line_id.product_id", readonly=False)
    usage_mode = fields.Selection(related="material_line_id.usage_mode")
    standard_length_in = fields.Float(related="material_line_id.standard_length_in")
    standard_width_in = fields.Float(related="material_line_id.standard_width_in")
    actual_length_in = fields.Float(related="material_line_id.actual_length_in", readonly=False)
    actual_width_in = fields.Float(related="material_line_id.actual_width_in", readonly=False)
    suggested_qty = fields.Float(related="material_line_id.suggested_qty")
    quantity = fields.Float(related="material_line_id.quantity", readonly=False)
    used_uom_id = fields.Many2one(related="material_line_id.used_uom_id")
    lot_id = fields.Many2one(related="material_line_id.lot_id", readonly=False)
    branch_available_qty = fields.Float(related="material_line_id.branch_available_qty")
    material_stock_warning = fields.Char(related="material_line_id.material_stock_warning")
    dimension_warning = fields.Char(related="material_line_id.dimension_warning")

    @api.onchange("material_brand_id")
    def _onchange_preparation_brand(self):
        if self.product_id and self.product_id.material_brand_id != self.material_brand_id:
            self.product_id = False
            self.lot_id = False

    @api.onchange("product_id", "actual_length_in", "actual_width_in", "quantity", "lot_id")
    def _onchange_preparation_material(self):
        self._check_preparation_read_access()
        line = self._origin.sudo().material_line_id
        if not (line and self.product_id):
            self.branch_available_qty = 0
            self.material_stock_warning = False
            return
        product = self.product_id
        preview_values = {"workorder_id": line.workorder_id.id, "product_id": product.id,
                          "used_uom_id": (line.used_uom_id if line.usage_mode == "quantity" else product.uom_id).id,
                          "quantity": self.quantity, "lot_id": self.lot_id.id}
        preview = line.new(preview_values, origin=line)
        if self.usage_mode == "roll" and product.film_width_in and product.roll_length_m and product.uom_id.rounding <= 0.0001:
            preview.update({"film_width_in": product.film_width_in, "roll_length_m": product.roll_length_m})
            preview.quantity = preview._film_quantity(self.actual_length_in, self.actual_width_in)
            self.quantity = preview.quantity
        elif self.usage_mode == "quantity" and not line.product_id:
            preview.quantity = line.suggested_qty
        self.branch_available_qty = preview.branch_available_qty
        self.material_stock_warning = preview.material_stock_warning
        if preview.material_stock_warning and not preview.availability_warehouse_id.workshop_stock_warning_only:
            return {"warning": {"title": _("Material Availability"), "message": preview.material_stock_warning}}

    def _check_preparation_read_access(self):
        self._origin.check_access_rights("read")
        self._origin.check_access_rule("read")

    def write(self, vals):
        if set(vals) - _EDITABLE_MATERIAL:
            raise AccessError(_("Only the selected material and actual usage can be changed."))
        self.check_access_rights("write")
        self.check_access_rule("write")
        for row in self:
            row.preparation_id._editable_request()
            line = row.sudo().material_line_id
            changes = dict(vals)
            product = self.env["product.product"].browse(changes.get("product_id", line.product_id.id))
            if "material_brand_id" in changes and "product_id" not in changes and product.material_brand_id.id != changes["material_brand_id"]:
                changes["product_id"] = False
                product = self.env["product.product"]
            if "product_id" in changes and product != line.product_id:
                changes.setdefault("lot_id", False)
                if line.usage_mode == "quantity":
                    if product and line.used_uom_id and product.uom_id.category_id != line.used_uom_id.category_id:
                        raise UserError(_("Choose a material compatible with the configured quantity unit."))
                    if line.used_uom_id:
                        changes["used_uom_id"] = line.used_uom_id.id
                    changes.setdefault("quantity", line.suggested_qty if product and not line.product_id else line.quantity if product else 0)
            if "product_id" in changes:
                brand = changes.get("material_brand_id", line.material_brand_id.id)
                if product and not brand:
                    raise UserError(_("Choose an approved brand before selecting a material."))
                if not product:
                    changes.setdefault("material_brand_id", brand)
            line.with_context(workshop_preparation_edit=_PREPARATION_EDIT, contract_upsell_sync=True).write(changes)
            row.invalidate_recordset()
        return True
