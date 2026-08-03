from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    external_referral_percent = fields.Float(
        string="External Referral (%)",
        digits=(5, 2),
        help=(
            "Percentage granted to this external agency salesperson. "
            "It is copied to an Extern sale order when this salesperson is selected."
        ),
    )

    def _check_external_referral_percent_access(self, values):
        if (
            "external_referral_percent" in values
            and not self.env.su
            and not self.env.user.has_group("sales_team.group_sale_manager")
        ):
            raise AccessError(_(
                "Only Sales Managers can set an external referral percentage."
            ))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._check_external_referral_percent_access(values)
        return super().create(vals_list)

    def write(self, values):
        self._check_external_referral_percent_access(values)
        return super().write(values)

    @api.constrains("external_referral_percent")
    def _check_external_referral_percent(self):
        for partner in self:
            if not 0 <= partner.external_referral_percent <= 100:
                raise ValidationError(_(
                    "External referral percentage must be between 0%% and 100%%."
                ))
