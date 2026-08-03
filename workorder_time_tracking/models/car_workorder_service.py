from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CarWorkorderService(models.Model):
    _inherit = "car.workorder.service"

    time_log_ids = fields.One2many(
        "car.workorder.service.time.log",
        "service_id",
        string="Time Logs",
        copy=False,
    )
    time_log_count = fields.Integer(
        compute="_compute_time_log_count",
    )

    @api.depends("time_log_ids")
    def _compute_time_log_count(self):
        for service in self:
            service.time_log_count = len(service.time_log_ids)

    def _get_open_time_log(self):
        self.ensure_one()
        return self.time_log_ids.filtered(lambda log: not log.date_end)[:1]

    def _get_finish_reason(self):
        reason = self.env.ref(
            "workorder_time_tracking.pause_reason_finished",
            raise_if_not_found=False,
        )
        if reason:
            return reason
        return self.env["workorder.pause.reason"].search(
            [("is_finish", "=", True)],
            limit=1,
        )

    def _open_time_log(self):
        self.ensure_one()
        open_log = self._get_open_time_log()
        if open_log:
            return open_log
        return self.env["car.workorder.service.time.log"].create({
            "service_id": self.id,
            "date_start": fields.Datetime.now(),
        })

    def _close_open_time_log(self, reason=False, reason_note=False):
        self.ensure_one()
        open_log = self._get_open_time_log()
        if open_log:
            open_log.write({
                "date_end": fields.Datetime.now(),
                "pause_reason_id": reason.id if reason else False,
                "pause_reason_note": reason_note or False,
            })
        return open_log

    def action_start(self):
        """Start or resume work and open a new time log interval."""
        self.ensure_one()
        # Keep legacy pause accounting in sync for existing reports.
        if self.pause_start:
            now = fields.Datetime.now()
            self.pause_duration += (now - self.pause_start).total_seconds()
            self.pause_start = False
        elif not self.date_start:
            self.date_start = fields.Datetime.now()

        if self.state == "done":
            raise UserError(_("You cannot restart a finished task."))

        self._open_time_log()
        self.state = "progress"
        self.message_post(body=_("Work started / resumed."))
        return True

    def action_break(self):
        """Ask for a pause reason, then stop the current interval."""
        self.ensure_one()
        if self.state != "progress":
            raise UserError(_("You can only pause a task that is in progress."))
        if not self._get_open_time_log() and not self.pause_start:
            # Fallback: allow pause even if an old record has no open log yet.
            self._open_time_log()
        return {
            "type": "ir.actions.act_window",
            "name": _("Pause Reason"),
            "res_model": "workorder.pause.reason.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_service_id": self.id,
                "active_id": self.id,
            },
        }

    def action_confirm_pause(self, reason, reason_note=False):
        """Close the open interval with a reason and mark task waiting."""
        self.ensure_one()
        if not reason:
            raise UserError(_("Please select a pause reason."))
        note = (reason_note or "").strip()
        if reason.requires_note and not note:
            raise UserError(
                _("Please enter a note for reason: %s") % reason.name
            )

        now = fields.Datetime.now()
        self._close_open_time_log(reason=reason, reason_note=note)
        self.pause_start = now
        self.state = "waiting"

        if note:
            body = _("Work paused.<br/>Reason: %(reason)s<br/>Note: %(note)s") % {
                "reason": reason.name,
                "note": note,
            }
        else:
            body = _("Work paused.<br/>Reason: %s") % reason.name
        self.message_post(body=body)
        return True

    def action_finish(self):
        """Finish the task and close any open time interval."""
        self.ensure_one()
        now = fields.Datetime.now()
        if self.pause_start:
            self.pause_duration += (now - self.pause_start).total_seconds()
            self.pause_start = False

        finish_reason = self._get_finish_reason()
        open_log = self._get_open_time_log()
        if open_log:
            open_log.write({
                "date_end": now,
                "pause_reason_id": finish_reason.id if finish_reason else False,
                "pause_reason_note": False,
            })
        elif self.state == "progress":
            start = self.date_start or now
            self.env["car.workorder.service.time.log"].create({
                "service_id": self.id,
                "date_start": start,
                "date_end": now,
                "pause_reason_id": finish_reason.id if finish_reason else False,
            })

        self.date_end = now
        self.state = "done"
        self.message_post(body=_("Work finished."))
        return True

    @api.depends("date_start", "date_end", "pause_duration", "time_log_ids.duration_hours")
    def _compute_duration_hours(self):
        for rec in self:
            logs = rec.time_log_ids.filtered(lambda log: log.date_end)
            if logs:
                rec.duration_hours = sum(logs.mapped("duration_hours"))
            elif rec.date_start and rec.date_end:
                total_seconds = (rec.date_end - rec.date_start).total_seconds()
                total_seconds -= rec.pause_duration or 0.0
                rec.duration_hours = max(total_seconds, 0) / 3600.0
            else:
                rec.duration_hours = 0.0
