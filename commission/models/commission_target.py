from odoo import fields, models


class CommissionTargetJob(models.Model):
    _name = "commission.target.job"
    _description = "Commission target job"
    _rec_name = "job_id"

    commission_id = fields.Many2one("commission", string="Commission")

    job_id = fields.Many2one("hr.job")
    target = fields.Float()


class CommissionTargetEmployee(models.Model):
    _name = "commission.target.employee"
    _description = "Commission target employee"
    _rec_name = "employee_id"

    commission_id = fields.Many2one("commission", string="Commission")

    employee_id = fields.Many2one("hr.employee")
    target = fields.Float()
