from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    deferred_start_date = fields.Date(
        string="Deferred Start Date",
        help="Start of the revenue recognition period.",
    )
    deferred_end_date = fields.Date(
        string="Deferred End Date",
        help="End of the revenue recognition period.",
    )

    @api.constrains("deferred_start_date", "deferred_end_date")
    def _check_deferred_dates(self):
        for line in self:
            if line.deferred_start_date and line.deferred_end_date:
                if line.deferred_end_date < line.deferred_start_date:
                    raise ValidationError(
                        _(
                            "Deferred End Date must be on or after Deferred Start Date "
                            "on invoice line '%(name)s'."
                        )
                        % {"name": line.display_name}
                    )

    def _is_deferred_revenue_line(self):
        self.ensure_one()
        return bool(
            self.deferred_start_date
            and self.deferred_end_date
            and self.display_type not in ("line_section", "line_note")
        )
