from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    donation_debit_account_id = fields.Many2one("account.account")
    donation_credit_account_id = fields.Many2one("account.account")
    donation_journal_id = fields.Many2one("account.journal")

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)

        if view_type == "form":
            for node in arch.xpath("//field[@name='name']"):
                if "widget" in node.attrib:
                    del node.attrib["widget"]
        return arch, view


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    donation_debit_account_id = fields.Many2one(
        "account.account", related="company_id.donation_debit_account_id", readonly=False
    )
    donation_credit_account_id = fields.Many2one(
        "account.account", related="company_id.donation_credit_account_id", readonly=False
    )
    donation_journal_id = fields.Many2one("account.journal", related="company_id.donation_journal_id", readonly=False)
