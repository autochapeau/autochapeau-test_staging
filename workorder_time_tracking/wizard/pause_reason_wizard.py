from odoo import _, fields, models
from odoo.exceptions import UserError


class WorkorderPauseReasonWizard(models.TransientModel):
    _name = "workorder.pause.reason.wizard"
    _description = "Workorder Pause Reason Wizard"

    service_id = fields.Many2one(
        "car.workorder.service",
        string="Task",
        required=True,
        ondelete="cascade",
    )
    pause_reason_id = fields.Many2one(
        "workorder.pause.reason",
        string="Pause Reason",
        required=True,
        domain="[('is_finish', '=', False)]",
    )
    pause_reason_note = fields.Text(
        string="Note",
        help="Optional details. Required when the selected reason requires a note.",
    )

    def action_confirm(self):
        self.ensure_one()
        note = (self.pause_reason_note or "").strip()
        if self.pause_reason_id.requires_note and not note:
            raise UserError(
                _("Please enter a note for reason: %s") % self.pause_reason_id.name
            )
        self.service_id.action_confirm_pause(
            self.pause_reason_id,
            note,
        )
        return {"type": "ir.actions.act_window_close"}
