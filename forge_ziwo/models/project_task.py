from odoo import models, fields, api, _
from datetime import timedelta


class ProjectTask(models.Model):
    _inherit = "project.task"

    partner_parent = fields.Many2one(related="partner_id.parent_id", string="Company")
    partner_phone = fields.Char(related="partner_id.phone", string="Phone")
    partner_mobile = fields.Char(related="partner_id.mobile", string="Mobile")

    ziwo_show_c2c_d2c = fields.Boolean(compute='_compute_ziwo_show_c2c_d2c')
    def _compute_ziwo_show_c2c_d2c(self):
        for record in self:
            record.ziwo_show_c2c_d2c = record._name in record.env['ziwo.active.form'].sudo().search([]).mapped('model_id.model')

    #override on create to capture the two see if two context values exist (ziwo_model and ziwo_record)
    @api.model
    def create(self, vals):
        res = super(ProjectTask, self).create(vals)
        ziwo_model = self.env.context.get('ziwo_model')
        ziwo_record = self.env.context.get('ziwo_record')
        if ziwo_model and ziwo_record:
            self.env['ziwo.history'].sudo().search([('id', '=', ziwo_record)]).update_call_model_reference('project.task', res.id)
        return res

    def action_add_note(self):
        return {
            "name": "Add Note",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "target": "new",
            "res_model": "add.note.wizard",
            "context": {"default_task_id": self.id},
        }

    def action_view_task(self):
        self.env['agent.screen'].sudo().update_call_model('project.task', self.id)
        return {
            "name": "View Task",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "views": [[False, "form"]],
            "target": "current",
            "res_model": "project.task",
            "res_id": self.id
        }
    
    def open_create_call_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "create.call.wizard",
            "view_mode": "form",
            "view_type": "form",
            "target": "new",
            "context": {
                "default_model": 'project.task',
                "default_record": self.id,
            },
        }

    def create_new_call(self):
        self.env['agent.screen'].sudo().create_new_call('project.task', self.id, self.partner_id.mobile_trim)
    
    def create_new_call_phone(self):
        self.env['agent.screen'].sudo().create_new_call('project.task', self.id, self.partner_id.phone_trim)