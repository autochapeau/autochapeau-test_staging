from odoo import fields, models


class CarAppointment(models.Model):
    _inherit = "car.appointment"

    branch_id = fields.Many2one(
        'hr.department',
        string='Branch',
        domain="[('department_type', '=', 'branche')]",
        help="Branch linked to the appointment."
    )
    car_work_order_id = fields.Many2one(
        "car.work.order", readonly=True, copy=False)

    def _work_order_service_materials(self, service):
        return [
            fields.Command.create({
                "service_id": bom.service_id.id,
                "product_id": bom.product_id.id,
                "quantity": bom.quantity,
            })
            for bom in service.bom_ids
        ]

    def action_done(self):
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM car_appointment WHERE id = %s FOR UPDATE", (self.id,))
        self.invalidate_recordset(["state", "car_work_order_id"])
        if self.state == "confirmed" and self.car_work_order_id:
            return True
        res = super().action_done()
        # Create a work order
        if not self.car_work_order_id:
            # services from appointment, products from bom
            services = []
            products = []
            for service in self.service_ids:
                services.append(
                    (
                        0,
                        0,
                        {
                            "product_id": service.product_id.id,
                            "expected_duration": service.product_id.expected_duration,
                            "workshop_id": service.product_id.workshop_id.id,
                        },
                    )
                )
                products.extend(self._work_order_service_materials(service.product_id))
            for line in self.product_ids:
                products.append(
                    (0, 0, {"product_id": line.product_id.id, "quantity": line.quantity}))
            work_order_vals = {
                "appointment_id": self.id,
                "partner_id": self.partner_id.id,
                "vehicle_id": self.vehicle_id.id,
                "company_id": self.company_id.id,
                "branch_id": self.branch_id.id,
                "service_ids": services,
                "product_ids": products,
            }
            car_work_order = self.env["car.work.order"].sudo().create(
                work_order_vals)
            self.car_work_order_id = car_work_order.id
        return res
