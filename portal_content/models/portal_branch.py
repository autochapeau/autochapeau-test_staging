from odoo import api, fields, models

WEEK_DAYS = [
    ("saturday", "Saturday"),
    ("sunday", "Sunday"),
    ("monday", "Monday"),
    ("tuesday", "Tuesday"),
    ("wednesday", "Wednesday"),
    ("thursday", "Thursday"),
    ("friday", "Friday"),
]


class PortalBranch(models.Model):
    _name = "portal.branch"
    _inherit = "image.mixin"
    _description = "Portal Branch"
    _order = "sequence,id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    address = fields.Text(translate=True)
    map_url = fields.Char()
    schedule_ids = fields.One2many("portal.branch.schedule", "branch_id")


class PortalBranchSchedule(models.Model):
    _name = "portal.branch.schedule"
    _description = "Portal Branch Schedule"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    branch_id = fields.Many2one("portal.branch", required=True, ondelete="cascade")
    day = fields.Selection(WEEK_DAYS, required=True)
    hour_from = fields.Float(string="From")
    hour_to = fields.Float(string="To")
    closed = fields.Boolean()

    _sql_constraints = [
        (
            "portal_branch_schedule_day_unique",
            "unique(branch_id, day)",
            "Each day can be added once per branch.",
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        day_sequence = {day: index * 10 for index, (day, _label) in enumerate(WEEK_DAYS)}
        for vals in vals_list:
            if not vals.get("sequence") and vals.get("day") in day_sequence:
                vals["sequence"] = day_sequence[vals["day"]]
        return super().create(vals_list)
