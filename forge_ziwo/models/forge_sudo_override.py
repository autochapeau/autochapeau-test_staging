from odoo import models, fields, api
from odoo.http import request

class ForgeSudoOverride(models.TransientModel):
    _name = "forge.sudo.override"
    _description = "Forge Sudo Override"

    @api.model
    def get_param_navigate_outbound_calls_c2c(self):
        return self.env.company.forge_ziwo_navigate_outbound_calls_c2c
    
    @api.model
    def create_act_window(self, result_action):
        action = self.env['ir.actions.act_window'].sudo().create(result_action)
        return action.id
    
    @api.model
    def create_client_notification(self, result_action):
        action = self.env['ir.actions.client'].sudo().create(result_action)
        return action.id
