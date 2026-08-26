from odoo import _, api, models
from odoo.exceptions import UserError


class CarWorkorderService(models.Model):
    _inherit = "car.workorder.service"

    def _check_sale_order_locked_lines(self):
        if self.env.context.get("contract_upsell_sync") or self.env.context.get("extern_upsell_sync"):
            return
        # Use .id so workshop users do not need sale.order ACL for this check.
        locked = self.filtered(lambda line: line.workorder_id.sale_order_id.id)
        if locked:
            raise UserError(_(
                "You cannot add or remove services on a work order "
                "linked to a sale order."
            ))

    @api.model_create_multi
    def create(self, vals_list):
        if not (
            self.env.context.get("contract_upsell_sync")
            or self.env.context.get("extern_upsell_sync")
        ):
            WorkOrder = self.env["car.work.order"]
            for vals in vals_list:
                workorder = WorkOrder.browse(vals.get("workorder_id"))
                if workorder.sale_order_id.id:
                    raise UserError(_(
                        "You cannot add services on a work order "
                        "linked to a sale order."
                    ))
        return super().create(vals_list)

    def unlink(self):
        self._check_sale_order_locked_lines()
        return super().unlink()
