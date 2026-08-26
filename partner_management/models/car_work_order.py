from odoo import _, fields, models
from odoo.exceptions import UserError


class CarWorkOrder(models.Model):
    _inherit = "car.work.order"

    task_count = fields.Integer(
        string="Tasks",
        compute="_compute_task_count",
    )
    sale_order_state = fields.Selection(
        related="sale_order_id.state",
        related_sudo=True,
        string="Sale Order Status",
    )
    sale_currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        related_sudo=True,
    )
    sale_split_amount_remaining = fields.Monetary(
        related="sale_order_id.split_amount_remaining",
        related_sudo=True,
        currency_field="sale_currency_id",
        string="Remaining to Collect",
    )
    sale_has_service_product_lines = fields.Boolean(
        related="sale_order_id.has_service_product_lines",
        related_sudo=True,
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

    def action_open_split_payment_wizard(self):
        """Collect payment on the linked sale order."""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_(
                "Collect Payment requires a sale order linked to this work order."
            ))
        return self.sale_order_id.action_open_split_payment_wizard()
