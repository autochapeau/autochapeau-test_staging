from odoo import fields, models


class WorkOrderQACheckItem(models.Model):
    _name = "workorder.qa.check.item"
    _description = "Work Order QA Check Item"

    qa_check_item_id = fields.Many2one(
        'qa.check.item', required=True, ondelete='cascade')
    checked = fields.Boolean()
    workorder_id = fields.Many2one(
        'car.work.order', required=True, ondelete='cascade')
