# -- coding: utf-8 --

from odoo import models, fields, api
import datetime


class AddNoteWizard(models.TransientModel):
    _name = 'add.note.wizard'
    _description = 'Add Note Wizard'

    opportunity_id = fields.Many2one(comodel_name="crm.lead", string="Opportunity")
    subscription_id = fields.Many2one(comodel_name="sale.order", string="Sale Order")
    task_id = fields.Many2one(comodel_name="project.task", string="Task")
    ziwo_history_id = fields.Many2one(comodel_name="ziwo.history", string="Call History")

    note = fields.Text(string="Note", required=True)

    def add_note(self):
        for record in self:
            if record.opportunity_id and record.note:
                record.opportunity_id.message_post(body=record.note)
            if record.subscription_id and record.note:
                record.subscription_id.message_post(body=record.note)
            if record.ziwo_history_id and record.note:
                record.ziwo_history_id.message_post(body=record.note)
            if record.task_id and record.note:
                record.task_id.message_post(body=record.note)
