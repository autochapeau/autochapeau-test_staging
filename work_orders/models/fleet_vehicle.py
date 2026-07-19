from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    workorder_count = fields.Integer(compute="_compute_workorder_count")

    def _compute_workorder_count(self):
        for vehicle in self:
            vehicle.workorder_count = self.env["car.work.order"].search_count([("vehicle_id", "=", vehicle.id)])

    def action_view_workorders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("work_orders.car_work_order_action")
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {"default_vehicle_id": self.id}
        return action
