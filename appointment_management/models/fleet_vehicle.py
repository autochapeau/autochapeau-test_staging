from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    appointment_count = fields.Integer(compute="_compute_appointment_count")

    def _compute_appointment_count(self):
        for vehicle in self:
            vehicle.appointment_count = self.env["car.appointment"].search_count([("vehicle_id", "=", vehicle.id)])

    def action_view_appointments(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("appointment_management.car_appointment_action")
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {"default_vehicle_id": self.id}
        return action
