from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _can_edit_salesperson(self):
        return self.env.su or self.env.user.has_group(
            "sale_salesperson_access.group_edit_salesperson"
        )

    def write(self, vals):
        if "user_id" in vals and not self._can_edit_salesperson():
            new_salesperson_id = vals["user_id"] or False
            changed = self.filtered(
                lambda order: (order.user_id.id or False) != new_salesperson_id
            )
            if changed:
                raise UserError(_(
                    "You are not allowed to change the salesperson on a sales order."
                ))
        return super().write(vals)
