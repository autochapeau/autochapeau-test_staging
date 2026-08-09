from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    qa_fault_journal_id = fields.Many2one(
        "account.journal",
        string="QA Fault Journal",
        help="Miscellaneous journal used to post QA fault cost allocation.",
    )
    qa_fault_technician_account_id = fields.Many2one(
        "account.account",
        string="QA Fault Technician Account",
        help="Receivable account for the technician share (Partner Ledger as customer).",
    )
    qa_fault_company_account_id = fields.Many2one(
        "account.account",
        string="QA Fault Company Expense Account",
        help="Expense account for the company share of the QA fault cost.",
    )
    qa_fault_offset_account_id = fields.Many2one(
        "account.account",
        string="QA Fault Offset Account",
        help="Credit account balancing the technician + company shares.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    qa_fault_journal_id = fields.Many2one(
        related="company_id.qa_fault_journal_id",
        readonly=False,
    )
    qa_fault_technician_account_id = fields.Many2one(
        related="company_id.qa_fault_technician_account_id",
        readonly=False,
    )
    qa_fault_company_account_id = fields.Many2one(
        related="company_id.qa_fault_company_account_id",
        readonly=False,
    )
    qa_fault_offset_account_id = fields.Many2one(
        related="company_id.qa_fault_offset_account_id",
        readonly=False,
    )
