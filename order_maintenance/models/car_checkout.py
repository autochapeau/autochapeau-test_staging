from odoo import models


class CarCheckout(models.Model):
    _inherit = "car.checkout"

    def _create_invoice_from_sale_order(self):
        """Customer-fault maintenance is invoiced. Technician and supplier faults are not."""
        self.ensure_one()
        claim = self.sale_order_id.maintenance_claim_id
        if claim and claim.fault_type in ("technician", "supplier"):
            return
        return super()._create_invoice_from_sale_order()
