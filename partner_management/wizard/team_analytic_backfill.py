from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class TeamAnalyticBackfill(models.TransientModel):
    _name = "team.analytic.backfill"
    _description = "Preview team analytics for selected historical records"

    sale_order_ids = fields.Many2many("sale.order", readonly=True)
    move_ids = fields.Many2many("account.move", readonly=True)
    eligible_count = fields.Integer(compute="_compute_counts")
    protected_count = fields.Integer(compute="_compute_counts")
    locked_count = fields.Integer(compute="_compute_counts")
    missing_team_count = fields.Integer(compute="_compute_counts")

    def _check_manager(self):
        self.ensure_one()
        for records, group in ((self.sale_order_ids, "sales_team.group_sale_manager"),
                               (self.move_ids, "account.group_account_manager")):
            if records:
                if not self.env.su and not self.env.user.has_group(group):
                    raise AccessError(_("A manager must review historical analytic updates."))
                records.check_access_rights("write")
                records.check_access_rule("write")

    def _planned_updates(self):
        self._check_manager()
        changes = []
        counts = {"protected": 0, "locked": 0, "missing_team": 0}
        lines = list(self.sale_order_ids.order_line.filtered(lambda line: not line.display_type))
        lines += list(self.move_ids.invoice_line_ids.filtered(lambda line: line.display_type == "product"))
        for line in lines:
            if line.company_id not in self.env.companies:
                raise AccessError(_("The selected records include a company outside your access."))
            line.check_access_rights("write")
            line.check_access_rule("write")
            if line._name == "account.move.line":
                move = line.move_id
                if move.move_type not in ("out_invoice", "out_refund") or move.state == "cancel":
                    counts["locked"] += 1
                    continue
                team = line.sale_line_ids.order_id.team_id or move.team_id
            else:
                team = line.order_id.team_id
                if line.order_id.state == "cancel":
                    counts["locked"] += 1
                    continue
            if len(team) != 1 or not team.sales_analytic_account_id:
                counts["missing_team"] += 1
                continue
            distribution, generated = team._merge_team_analytic_distribution(line.analytic_distribution, line.company_id)
            if not generated:
                counts["protected"] += 1
                continue
            changes.append((line, distribution, team.sales_analytic_account_id))
        return changes, counts

    @api.depends("sale_order_ids", "move_ids")
    def _compute_counts(self):
        for wizard in self:
            changes, counts = wizard._planned_updates()
            wizard.eligible_count = len(changes)
            wizard.protected_count = counts["protected"]
            wizard.locked_count = counts["locked"]
            wizard.missing_team_count = counts["missing_team"]

    def _open_preview(self):
        self.ensure_one()
        self._check_manager()
        return {"type": "ir.actions.act_window", "res_model": self._name,
                "res_id": self.id, "view_mode": "form", "target": "new",
                "name": _("Review Team Analytics")}

    def action_apply(self):
        self.ensure_one()
        changes, counts = self._planned_updates()
        for line, distribution, account in changes:
            values = {"analytic_distribution": distribution}
            if line._name == "sale.order.line":
                values["sales_team_analytic_account_id"] = account.id
            line.write(values)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Team Analytics"), "type": "success",
                           "message": _("Updated %s lines. Existing allocations, invoice amounts and taxes were kept.") % len(changes),
                           "next": {"type": "ir.actions.act_window_close"}}}
