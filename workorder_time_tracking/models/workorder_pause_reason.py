from odoo import fields, models


class WorkorderPauseReason(models.Model):
    _name = "workorder.pause.reason"
    _description = "Workorder Pause Reason"
    _order = "sequence, name, id"

    name = fields.Char(string="Reason", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    requires_note = fields.Boolean(
        string="Requires Note",
        help="If checked, the technician must enter a note when pausing with this reason.",
    )
    is_finish = fields.Boolean(
        string="Finish Reason",
        help="Used automatically when finishing a task. Hidden from the pause wizard.",
        default=False,
        copy=False,
    )
