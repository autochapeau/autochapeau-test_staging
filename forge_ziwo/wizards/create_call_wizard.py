# -- coding: utf-8 --

from odoo import models, fields, api
import datetime


class CreateCallWizard(models.TransientModel):
    _name = 'create.call.wizard'
    _description = 'Create Call Wizard'

    mobile = fields.Char(string="Mobile")
    mobile_trim = fields.Char(compute="_trim_number", store=True)
    model = fields.Char(string="Model")
    record = fields.Integer(string="Record")
    

    @api.depends('mobile')
    def _trim_number(self):
        for record in self:
            record["mobile_trim"] = record["mobile"]
            if record["mobile"]:
                record["mobile_trim"] = record["mobile"].replace(' ', '')

    def create_call(self):
        self.ensure_one()
        if self.model or self.record:
            self.env['agent.screen'].sudo().create_new_call(self.model, self.record, self.mobile_trim)
        else:
            self.env['agent.screen'].sudo().create_new_call(False, False, self.mobile_trim)

    def cancel(self):
        self.unlink()
        return {'type': 'ir.actions.act_window_close'}