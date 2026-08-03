from odoo import api, models


class CarAppointment(models.Model):
    _inherit = "car.appointment"

    @api.model_create_multi
    def create(self, vals_list):
        appointments = super().create(vals_list)
        for appointment in appointments:
            sale = appointment.sale_order_id
            if not sale or sale.order_type != "extern":
                continue
            sale.child_sale_ids.filtered(
                lambda order: order.state != "cancel"
            )._sync_extern_upsell_to_appointment()
        return appointments

    def action_done(self):
        """After the shared WO is created, sync any already-confirmed upsells."""
        result = super().action_done()
        for appointment in self:
            sale = appointment.sale_order_id
            if not sale or sale.order_type != "extern":
                continue
            extras = sale.child_sale_ids.filtered(
                lambda order: order.state != "cancel"
            )
            extras._sync_extern_upsell_to_visit()
        return result
