from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    appointment_slot_id = fields.Many2one(
        "car.appointment.slot", readonly=True)
    vehicle_id = fields.Many2one("fleet.vehicle", readonly=True)
    cart_id = fields.Char(readonly=True)
    # One to One mapping: appointment_id <--> sale_order_id
    appointment_id = fields.Many2one("car.appointment")

    def action_confirm(self):
        """Generate the related appointment."""
        # First call super to generate the sale order name
        result = super().action_confirm()

        # Re-use an appointment already linked to order via sale_order_id
        # to avoid creating a duplicate.
        existing = self.env["car.appointment"].sudo().search(
            [("sale_order_id", "=", self.id)], limit=1)
        if existing and not self.appointment_id:
            self.write({"appointment_id": existing.id})

        # Then create the appointment only if none exists yet
        if not self.appointment_id and self.appointment_slot_id and self.vehicle_id:
            appointment_vals = {
                "partner_id": self.partner_id.id,
                "vehicle_id": self.vehicle_id.id,
                "appointment_slot_id": self.appointment_slot_id.id,
                "company_id": self.appointment_slot_id.company_id.id,
                "branch_id": self.branch_id.id if self.branch_id else False,
                "sale_order_id": self.id,
            }
            services = self.order_line.mapped("product_id").filtered(
                lambda p: p.detailed_type == "service")
            if services:
                appointment_vals["service_ids"] = [
                    (0, 0, {"product_id": service.id}) for service in services]
            product_lines = self.order_line.filtered(
                lambda line: line.product_id.detailed_type != "service")
            if product_lines:
                appointment_vals["product_ids"] = [
                    (0, 0, {"product_id": line.product_id.id,
                     "quantity": line.product_uom_qty})
                    for line in product_lines
                ]
            appointment = self.env["car.appointment"].sudo().create(
                appointment_vals)
            self.write({"appointment_id": appointment.id})

        return result

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals['vehicle_id'] = self.vehicle_id.id
        return invoice_vals
