from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _program_check_compute_points(self, programs):
        """Grant loyalty points according to the customer's membership level.

        If the order's customer has a membership grant configured on the rule,
        use it instead of the rule's default grant. Falls back to the default
        grant when the customer's membership has no specific line.
        """
        result = super()._program_check_compute_points(programs)
        partner = self.partner_id
        if partner.is_company or not partner.membership_id:
            return result
        membership = partner.membership_id
        for program in programs:
            program_result = result.get(program)
            if not program_result or "points" not in program_result:
                continue
            if len(program.rule_ids) != 1:
                continue
            rule = program.rule_ids
            line = rule.membership_point_ids.filtered(
                lambda mp: mp.membership_id == membership
            )[:1]
            points = program_result.get("points")
            if not line or not rule.reward_point_amount:
                continue
            factor = line.reward_point_amount / rule.reward_point_amount
            if isinstance(points, list):
                program_result["points"] = [p * factor for p in points]
            elif isinstance(points, (int, float)):
                program_result["points"] = points * factor
        return result
