from odoo import _, api, fields, models


class CarWorkorderServiceTimeLog(models.Model):
    _name = "car.workorder.service.time.log"
    _description = "Workorder Service Time Log"
    _order = "date_start desc, id desc"

    service_id = fields.Many2one(
        "car.workorder.service",
        string="Task",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date_start = fields.Datetime(string="Start", required=True, readonly=True)
    date_end = fields.Datetime(string="End", readonly=True)
    pause_reason_id = fields.Many2one(
        "workorder.pause.reason",
        string="Pause Reason",
        readonly=True,
        ondelete="restrict",
    )
    pause_reason_note = fields.Text(
        string="Pause Note",
        readonly=True,
    )
    pause_reason = fields.Char(
        string="Pause / Stop Reason",
        compute="_compute_pause_reason",
        store=True,
    )
    duration_hours = fields.Float(
        string="Duration (hours)",
        compute="_compute_duration_hours",
        store=True,
    )
    is_open = fields.Boolean(
        string="Open",
        compute="_compute_is_open",
        store=True,
    )

    @api.depends("pause_reason_id", "pause_reason_id.name", "pause_reason_note")
    def _compute_pause_reason(self):
        for log in self:
            label = log.pause_reason_id.name or ""
            note = (log.pause_reason_note or "").strip()
            if label and note:
                log.pause_reason = f"{label}: {note}"
            else:
                log.pause_reason = note or label or False

    @api.depends("date_start", "date_end")
    def _compute_duration_hours(self):
        for log in self:
            if log.date_start and log.date_end:
                seconds = (log.date_end - log.date_start).total_seconds()
                log.duration_hours = max(seconds, 0.0) / 3600.0
            else:
                log.duration_hours = 0.0

    @api.depends("date_end")
    def _compute_is_open(self):
        for log in self:
            log.is_open = not bool(log.date_end)
