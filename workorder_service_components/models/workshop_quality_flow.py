from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from .workshop_preparation import _MANAGER, _PREPARATION_EDIT, _TASK_TRANSITION


class Workshop(models.Model):
    _inherit = "car.workshop"

    quality_reviewer_ids = fields.Many2many(
        "res.users", "car_workshop_quality_reviewer_rel", "workshop_id", "user_id",
        string="Quality Reviewers",
        domain=lambda self: [("groups_id", "in", self.env.ref("work_orders.group_quality_officer").ids)],
    )
    final_check_item_ids = fields.Many2many(
        "qa.check.item", "car_workshop_final_check_item_rel", "workshop_id", "item_id",
        string="Final Workshop Checks",
    )


class ServiceProduct(models.Model):
    _inherit = "product.product"

    task_quality_check_item_ids = fields.Many2many(
        "qa.check.item", "product_workshop_task_check_item_rel", "product_id", "item_id",
        string="Task Quality Checks",
        help="Optional checklist for this variant. If it is empty, the service uses its configured product features.",
    )
    skip_task_quality = fields.Boolean(
        string="Skip Task Quality", help="Do not send this service variant to task quality in the workshop flow.",
    )


class ServiceCheckItem(models.Model):
    _inherit = "workorder.service.qa.check.item"

    item_type = fields.Selection(selection_add=[("checklist", "Checklist")], ondelete={"checklist": "set default"})
    workshop_check_item_id = fields.Many2one("qa.check.item", ondelete="set null")

    def write(self, vals):
        if "checked" in vals:
            self.mapped("service_id")._check_workshop_quality_actor()
        return super().write(vals)


class FinalCheckItem(models.Model):
    _inherit = "workorder.qa.check.item"

    def write(self, vals):
        if "checked" in vals:
            orders = self.sudo().workorder_id.filtered("material_preparation_enabled")
            if orders and not (self.env.su or self.env.user.has_group(_MANAGER)):
                raise AccessError(_("Only the workshop manager can complete the general inspection."))
            if orders.filtered(lambda order: order.state != "quality"):
                raise UserError(_("The general inspection is available after all service tasks are finished."))
        return super().write(vals)


class WorkOrder(models.Model):
    _inherit = "car.work.order"

    def action_quality(self):
        self.ensure_one()
        if not self.material_preparation_enabled:
            return super().action_quality()
        self._check_workshop_manager()
        self._lock_workshop_flow()
        if self.state != "progress" or not self.all_tasks_done:
            raise UserError(_("Finish all work and task quality reviews before opening the general inspection."))
        return super(WorkOrder, self.with_context(workshop_flow_transition=_PREPARATION_EDIT)).action_quality()

    def _ensure_qa_check_items(self):
        legacy = self.filtered(lambda order: not order.material_preparation_enabled)
        if legacy:
            super(WorkOrder, legacy)._ensure_qa_check_items()
        Check = self.env["workorder.qa.check.item"].sudo()
        for order in self - legacy:
            if order.sudo().qa_check_item_ids:
                continue
            workshops = order.service_ids.filtered(lambda task: task.state != "cancel").workshop_id
            checks = workshops.sudo().final_check_item_ids.filtered("active")
            Check.create([{"workorder_id": order.id, "qa_check_item_id": check.id} for check in checks])

    def action_confirm_quality(self):
        self.ensure_one()
        if self.material_preparation_enabled:
            self._check_workshop_manager()
            self._lock_workshop_flow()
            if self.state != "quality" or not self.all_tasks_done:
                raise UserError(_("Open the general inspection after all services have finished."))
            if self.sudo().qa_check_item_ids.filtered(lambda item: not item.checked):
                raise UserError(_("Complete every general inspection item before approving."))
        return super(WorkOrder, self.with_context(workshop_flow_transition=_PREPARATION_EDIT)).action_confirm_quality()

    def action_done(self):
        self.ensure_one()
        if self.material_preparation_enabled:
            self._check_workshop_manager()
            self._lock_workshop_flow()
            if self.state != "quality_confirmed":
                raise UserError(_("Approve the general workshop inspection before closing the order."))
        return super(WorkOrder, self.with_context(workshop_flow_transition=_PREPARATION_EDIT)).action_done()


class WorkOrderService(models.Model):
    _inherit = "car.workorder.service"

    def _check_workshop_quality_actor(self):
        if self.env.su or self.env.user.has_group(_MANAGER):
            return
        user = self.env.user
        for task in self.sudo().filtered(lambda task: task.workorder_id.material_preparation_enabled):
            if (task.state != "quality" or not user.has_group("work_orders.group_quality_officer")
                    or user not in task.workshop_id.quality_reviewer_ids or task.workorder_id.company_id not in self.env.companies):
                raise AccessError(_("Only a reviewer assigned to this workshop can inspect the pending task."))

    def _has_quality_checklist(self):
        self.ensure_one()
        if self.workorder_id.sudo().material_preparation_enabled:
            product = self.product_id.sudo()
            if product.skip_task_quality:
                return False
            return bool(product.task_quality_check_item_ids.filtered("active") or self._get_product_features()
                        or self.sudo().qa_check_item_ids)
        return super()._has_quality_checklist()

    def _get_service_boms(self):
        self.ensure_one()
        if self.workorder_id.sudo().material_preparation_enabled:
            return self.env["car.bom"]
        return super()._get_service_boms()

    def _ensure_qa_items(self):
        configured = self.filtered(lambda task: task.workorder_id.sudo().material_preparation_enabled
                                   and task.product_id.sudo().task_quality_check_item_ids.filtered("active"))
        standard = self - configured
        result = super(WorkOrderService, standard)._ensure_qa_items() if standard else None
        Check = self.env["workorder.service.qa.check.item"].sudo()
        for task in configured:
            if task.sudo().qa_check_item_ids:
                continue
            checks = task.product_id.sudo().task_quality_check_item_ids.filtered("active")
            Check.create([{"service_id": task.id, "item_type": "checklist",
                           "workshop_check_item_id": check.id, "name": check.name} for check in checks])
        return result

    def action_confirm_quality(self):
        self._check_workshop_quality_actor()
        return super(WorkOrderService, self.with_context(workshop_task_transition=_TASK_TRANSITION)).action_confirm_quality()

    def action_refuse_quality(self):
        self._check_workshop_quality_actor()
        return super().action_refuse_quality()

    def action_apply_quality_refuse(self, *args, **kwargs):
        self._check_workshop_quality_actor()
        return super(WorkOrderService, self.with_context(workshop_task_transition=_TASK_TRANSITION)).action_apply_quality_refuse(*args, **kwargs)
