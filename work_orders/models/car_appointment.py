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

    def action_done(self):
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
                        },
                    )
                )
                for bom in service.product_id.bom_ids:
                    products.append(
                        (
                            0,
                            0,
                            {
                                "service_id": bom.service_id.id,
                                "product_id": bom.product_id.id,
                                "quantity": bom.quantity,
                            },
                        )
                    )
            for line in self.product_ids:
                products.append(
                    (0, 0, {"product_id": line.product_id.id, "quantity": line.quantity}))
            work_order_vals = {
                "appointment_id": self.id,
                "partner_id": self.partner_id.id,
                "vehicle_id": self.vehicle_id.id,
                "company_id": self.company_id.id,
                # 'branch_id' removed because car.work.order does not have this field
                "service_ids": services,
                "product_ids": products,
            }
            car_work_order = self.env["car.work.order"].sudo().create(
                work_order_vals)
            self.car_work_order_id = car_work_order.id
        return res
