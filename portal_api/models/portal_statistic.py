from odoo import models


class PortalStatistic(models.Model):
    _inherit = "portal.statistic"

    def _website_value(self):
        self.ensure_one()
        if self.metric == "manual":
            return super()._website_value()
        tasks = self.env["car.workorder.service"].sudo().search([
            ("state", "=", "done"), ("date_end", ">=", self.count_from),
            ("workorder_id.state", "!=", "cancelled"),
        ])
        orders = tasks.mapped("workorder_id")
        if self.metric == "cars":
            if self.car_count_mode == "visits":
                count = len(orders)
            else:
                candidates = orders.mapped("vehicle_id")
                previous = self.env["car.workorder.service"].sudo().search([
                    ("state", "=", "done"), ("date_end", "<", self.count_from),
                    ("workorder_id.state", "!=", "cancelled"),
                    ("workorder_id.vehicle_id", "in", candidates.ids),
                ]).mapped("workorder_id.vehicle_id")
                count = len(candidates - previous)
        elif self.metric == "customers":
            candidates = orders.mapped("partner_id")
            previous = self.env["car.workorder.service"].sudo().search([
                ("state", "=", "done"), ("date_end", "<", self.count_from),
                ("workorder_id.state", "!=", "cancelled"),
                ("workorder_id.partner_id", "in", candidates.ids),
            ]).mapped("workorder_id.partner_id")
            count = len(candidates - previous)
        else:
            count = len(tasks)
        return str(self.opening_value + count)
