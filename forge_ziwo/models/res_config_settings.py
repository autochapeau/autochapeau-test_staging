# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo import fields, models
import requests
import json
import logging
_logger = logging.getLogger(__name__)  # Use standard logging


class Company(models.Model):
    _inherit = 'res.company'

    forge_ziwo_active_form_id = fields.Many2one('ziwo.active.form', string='Default Action')
    forge_ziwo_active_form_history = fields.Boolean(string='History on Active Form')
    forge_ziwo_navigate_outbound_calls = fields.Boolean(string='Navigate (Outbound Calls)')
    forge_ziwo_navigate_outbound_calls_c2c = fields.Boolean(string='Click to Call Override Navigate (Outbound Calls)')
    forge_ziwo_navigate_inbound_calls = fields.Boolean(string='Navigate (Inbound Calls)')
    forge_ziwo_admin_auth_token = fields.Char(string='Admin Auth Token')
    forge_ziwo_user_name_auth_token = fields.Char(string='User Name')
    forge_ziwo_password_auth_token = fields.Char(string='Password')
    forge_ziwo_account_name_auth_token = fields.Char(string='Account Name Token')
    forge_ziwo_contact_creation_mode = fields.Selection([
        ('auto', 'Automatic'),
        ('manual', 'Manual'),
    ], string='Contact Creation', default='auto', required=True)

    def update_ziwo_admin_auth_token(self):
        companies = self.search([])
        for company in companies:
            username = company.forge_ziwo_user_name_auth_token
            password = company.forge_ziwo_password_auth_token
            instancename = company.forge_ziwo_account_name_auth_token

            if not username or not password or not instancename:
                _logger.warning("Missing credentials or instance name for company ID %s", company.id)
                continue

            url = f'https://{instancename}-api.aswat.co/auth/login'

            payload = {
                "username": username,
                "password": password,
            }

            headers = {
                'Content-Type': 'application/json; charset=utf-8'
            }
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=15
                )
                response.raise_for_status()
                json_data = response.json()
                content_token = json_data.get('content')
                access_token = content_token.get('access_token')
                if access_token:
                    company.forge_ziwo_admin_auth_token = access_token
                    _logger.info("Access token successfully updated for company ID %s", company.id)
                else:
                    _logger.warning("No access_token in response for company ID %s", company.id)
            except requests.exceptions.RequestException as e:
                _logger.error("Request error for company ID %s: %s", company.id, str(e))
            except Exception as e:
                _logger.exception("Unexpected error for company ID %s", company.id)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    forge_ziwo_active_form_id = fields.Many2one('ziwo.active.form', string='Default Action', readonly=False,
                                                related='company_id.forge_ziwo_active_form_id')
    forge_ziwo_active_form_history = fields.Boolean(string='History on Active Form', readonly=False,
                                                    related='company_id.forge_ziwo_active_form_history')
    forge_ziwo_navigate_outbound_calls = fields.Boolean(string='Navigate (Outbound Calls)', readonly=False,
                                                        related='company_id.forge_ziwo_navigate_outbound_calls')
    forge_ziwo_navigate_outbound_calls_c2c = fields.Boolean(string='Click to Call Override Navigate (Outbound Calls)',
                                                            readonly=False,
                                                            related='company_id.forge_ziwo_navigate_outbound_calls_c2c')
    forge_ziwo_navigate_inbound_calls = fields.Boolean(string='Navigate (Inbound Calls)', readonly=False,
                                                       related='company_id.forge_ziwo_navigate_inbound_calls')
    forge_ziwo_admin_auth_token = fields.Char(string='Admin Auth Token', readonly=False,
                                              related='company_id.forge_ziwo_admin_auth_token')
    forge_ziwo_user_name_auth_token = fields.Char(string='User Name', readonly=False,
                                                  related='company_id.forge_ziwo_user_name_auth_token')
    forge_ziwo_password_auth_token = fields.Char(string='Password', readonly=False,
                                                 related='company_id.forge_ziwo_password_auth_token')
    forge_ziwo_account_name_auth_token = fields.Char(string='Account Name Token', readonly=False,
                                                     related='company_id.forge_ziwo_account_name_auth_token')
    forge_ziwo_contact_creation_mode = fields.Selection(related='company_id.forge_ziwo_contact_creation_mode',
                                                        string='Contact Creation', readonly=False)

    def action_update_ziwo_admin_auth_token(self):
        companies = self.env['res.company'].browse(self.env.companies.ids)
        for company in companies:
            if not company.forge_ziwo_account_name_auth_token:
                raise ValidationError("Account Name is required.")
            if not company.forge_ziwo_user_name_auth_token :
                raise ValidationError("User Name is required.")
            if not company.forge_ziwo_password_auth_token:
                raise ValidationError("Password is required.")
            original_token = company.forge_ziwo_admin_auth_token
            company.update_ziwo_admin_auth_token()
            if company.forge_ziwo_admin_auth_token and company.forge_ziwo_admin_auth_token != original_token:
                return {
                        'effect': {
                            'fadeout': 'slow',
                            'message': 'Access token generated successfully!',
                            'type': 'rainbow_man'
                        }
                    }
