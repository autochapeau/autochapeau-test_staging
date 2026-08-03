from odoo import _, fields, models


class CarWorkOrder(models.Model):
    _inherit = "car.work.order"

    task_count = fields.Integer(
        string="Tasks",
        compute="_compute_task_count",
    )

    def _compute_task_count(self):
        for work_order in self:
            work_order.task_count = len(work_order.service_ids)

    def action_view_tasks(self):
        """Show only the service tasks belonging to this work order."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "work_orders.car_workorder_service_action"
        )
        action["domain"] = [("workorder_id", "=", self.id)]
        action["context"] = {
            "default_workorder_id": self.id,
        }
        action["name"] = _("Tasks")
        return action
