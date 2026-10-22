from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime
import requests, base64, json

import logging

_logger = logging.getLogger(__name__)


class ZiwoHistory(models.Model):
    _name = 'ziwo.history'
    _description = 'Ziwo Call History'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    agent_id = fields.Many2one('res.users', string='Agent', readonly=True)
    agent_ids = fields.Many2many('res.users', string='Attending Agents', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Contact', readonly=True)
    partner_parent = fields.Many2one(related="partner_id.parent_id", string="Company")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    mobile = fields.Char(string='Mobile Number', readonly=True)
    call_type = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound')
    ], string='Call Type', readonly=True)
    call_status = fields.Selection([
        ('answered', 'Answered'),
        ('rejected', 'Rejected'),
        ('missed', 'Missed')
    ], string='Call Status', readonly=True)
    call_id = fields.Char(string='Call ID', readonly=True)
    call_time = fields.Datetime(string='Call Time', readonly=True)
    model_reference = fields.Reference(string='Model', selection='_get_model_selection')
    model_reference_model = fields.Char(string='Model', compute='_compute_model_reference')
    model_reference_record = fields.Char(string='Record', compute='_compute_record_reference', tracking=True)
    main_message_id = fields.Many2one('mail.message', string='Message')
    main_message_id_update = fields.Many2one('mail.message', string='Message')
    chatter_message_id = fields.Many2one('mail.message', string='Chatter Message')
    chatter_message_id_update = fields.Many2one('mail.message', string='Chatter Message')
    chatter_message_model = fields.Char(string='Chatter Message Model', related='chatter_message_id.model')
    chatter_message_record_id = fields.Many2oneReference(string='Chatter Message Record',
                                                         related='chatter_message_id.res_id')
    chatter_message_subject = fields.Char(string='Chatter Message Subject', related='chatter_message_id.subject')
    call_recording = fields.Char(string='Call Recording', readonly=True)
    call_recording_html = fields.Html(string='Call Recording', compute='_compute_call_recording_html',
                                      sanitize_attributes=False, readonly=True)
    call_transfer = fields.Boolean(string='Transfer', default=False, readonly=True)
    call_transfer_type = fields.Selection([
        ('blind', 'Blind'),
        ('attend', 'Attend')
    ], string='Transfer Type', readonly=True)

    @api.depends('model_reference')
    def _compute_model_reference(self):
        for record in self:
            if record.model_reference:
                model_name = self.env['ir.model'].sudo().search([('model', '=', record.model_reference._name)]).name
                record.model_reference_model = model_name
            else:
                record.model_reference_model = False

    @api.depends('model_reference')
    def _compute_record_reference(self):
        for record in self:
            if record.model_reference:
                model_name = self.env['ir.model'].sudo().search([('model', '=', record.model_reference._name)]).name
                record_name = self.env[record.model_reference._name].sudo().search(
                    [('id', '=', record.model_reference.id)]).display_name
                record.model_reference_record = model_name + ", " + record_name
            else:
                record.model_reference_record = False

    @api.model
    def _get_model_selection(self):
        selection = []
        active_forms = self.env['ziwo.active.form'].sudo().search([]).mapped('model_id')
        for model in active_forms:
            selection.append((model.model, model.name))
        return selection

    @api.depends('call_recording', 'call_id')
    def _compute_call_recording_html(self):
        for record in self:
            if record.call_recording:
                record.call_recording_html = '<audio name="media" controls="true" id="%s"><source src="%s" type="audio/mpeg"></audio>' % (
                    record.call_id, record.call_recording)
            else:
                record.call_recording_html = False

    def action_update_call_recording(self):
        message = {
            'action': 'get',
            'record': self.id,
        }
        self.env['bus.bus'].sudo()._sendone(self.env.user.partner_id, 'ziwo/bus', message)

    @api.model
    def create_call_recording(self, id, session):
        record = self.browse(id)

        if not session:
            raise UserError('ZIWO session expired. Please refresh the page.')

        admin_auth_token = self.env['ir.config_parameter'].sudo().get_param('forge_ziwo_admin_auth_token')

        instance_name = session['accountName']
        access_token = session['token']

        base_url = 'https://%s-api.aswat.co' % instance_name
        endpoint = f'/callHistory/{record.call_id}/recording/signed-url'
        _logger.info('ZIWO Call Recording URL: %s', base_url + endpoint)
        _logger.info('ZIWO Call Instance Name: %s', instance_name)
        _logger.info('ZIWO Call Session: %s', session)
        _logger.info('ZIWO Call Call ID: %s', record.call_id)

        if admin_auth_token:
            headers = {'access_token': admin_auth_token}
        else:
            headers = {'access_token': access_token}

        response = requests.get(base_url + endpoint, headers=headers)

        return_action = {}
        action_type = 'success'
        action_message = 'Call recording updated successfully'

        if response.status_code == 200:
            try:
                record.call_recording = json.loads(response.content.decode('utf-8'))['content']['url']
            except:
                action_type = 'danger'
                action_message = 'Error processing call recording'

        elif record.call_status == 'answered':
            error_message = json.loads(response.content.decode('utf-8'))['error']['message']
            action_type = 'danger'
            action_message = error_message

        if action_type == 'success' and record.call_recording and record.main_message_id:
            record.create_message(False, True)

        return {
            'action': {
                'type': 'ir.actions.client',
                'name': 'Call Recording Notification',
                'tag': 'display_notification',
                'params': {
                    'message': action_message,
                    'type': action_type,
                    'sticky': False,
                }
            }
        }

    def create_message(self, duplicate=False, update=False):
        subject = 'New call created'
        body = ''
        is_transfer_flag = False
        for field_name in ['agent_id', 'call_transfer', 'agent_ids', 'partner_id', 'mobile', 'call_type', 'call_time',
                           'call_status']:
            field_value = self[field_name]
            field_display_name = self._fields[field_name].string
            if field_name in ['agent_id', 'partner_id']:
                field_value = field_value.display_name if field_value else (self.mobile or 'Unknown')
            elif field_name == 'call_transfer':
                if not field_value:
                    continue
                is_transfer_flag = True
                field_value = 'Yes'
            elif field_name == 'agent_ids':
                if not is_transfer_flag:
                    continue
                field_value = ', '.join(field_value.mapped('display_name'))
            body += '<p><strong>%s:</strong> %s</p>' % (field_display_name, field_value)
        if self.call_recording:
            body += '<p><audio name="media" controls="true" id="%s"><source src="%s" type="audio/mpeg"></audio></p>' % (
                self.call_id, self.call_recording)
        message = self.env['mail.message'].sudo().create({
            'model': self._name,
            'res_id': self.id,
            'subject': subject,
            'body': body,
        })

        if update:
            if not self.main_message_id_update:
                self.main_message_id_update = message.id
            if self.model_reference and not self.chatter_message_id_update:
                self.chatter_message_id_update = message.id
                self.chatter_message_id_update.write({
                    'model': self.model_reference._name,
                    'res_id': self.model_reference.id,
                })
        else:
            if not duplicate:
                self.main_message_id = message.id
            else:
                self.chatter_message_id = message.id

        return True

    def action_apply_model(self):
        if not self.model_reference:
            raise UserError('Model or record cannot be empty')

        if not self.chatter_message_id and self.main_message_id:
            self.create_message(True)

        self.chatter_message_id.write({
            'model': self.model_reference._name,
            'res_id': self.model_reference.id,
        })

        return True

    @api.model
    def create_record(self, mobile, call_type, call_id, call_time, model_name, record_id):
        partner_id = self.env['res.partner'].sudo().search(
            ['|', ('mobile_trim', '=', mobile), ('phone_trim', '=', mobile)])
        if not partner_id and self.env.company.forge_ziwo_contact_creation_mode != 'manual':
            partner_id = self.env['res.partner'].sudo().create({
                'name': mobile,
                'mobile': mobile,
            })

        date_time = fields.Datetime.to_string(datetime.strptime(call_time, '%Y-%m-%dT%H:%M:%S.%fZ'))

        new_record_data = {
            'agent_id': self.env.user.id,
            'agent_ids': [(6, 0, [self.env.user.id])],
            'partner_id': partner_id.id,
            'mobile': mobile,
            'call_type': call_type,
            'call_id': call_id,
            'call_time': date_time,
        }

        if model_name and record_id:
            new_record_data['model_reference'] = '%s,%s' % (model_name, record_id) if model_name in self.env[
                'ziwo.active.form'].sudo().search([]).mapped('model_id.model') else False

        new_record = self.create(new_record_data)

        return new_record

    @api.model
    def create_call_record(self, mobile, call_type, call_id, call_time, model_name, record_id):
        new_record = self.create_record(mobile, call_type, call_id, call_time, model_name, record_id)
        action = new_record.send_to_agent()
        return {
            'record_id': new_record.id,
            'action': action,
        }

    @api.model
    def transfer_call_record(self, parent_call_id, transfer_type):
        search_parent_call = self.env['ziwo.history'].sudo().search([('call_id', '=', parent_call_id)])
        if search_parent_call:
            search_parent_call.call_transfer = True
            search_parent_call.call_transfer_type = transfer_type
            if transfer_type == 'blind':
                search_parent_call.agent_id = self.env.user.id
            elif transfer_type == 'attend':
                search_parent_call.agent_ids = [(6, 0, [self.env.user.id])]
        return search_parent_call.id

    @api.model
    def update_call_id(self, id, call_id, call_time):
        record = self.browse(id)
        record.call_id = call_id
        record.call_time = fields.Datetime.to_string(datetime.strptime(call_time, '%Y-%m-%dT%H:%M:%S.%fZ'))
        return record.id

    @api.model
    def update_call_status(self, id, call_status):
        record = self.browse(id)
        if record.call_status == False:
            record.call_status = call_status
        return record.id

    def update_call_model_reference(self, model_name, record_id):
        self.model_reference = '%s,%s' % (model_name, record_id) if model_name in self.env[
            'ziwo.active.form'].sudo().search([]).mapped('model_id.model') else False
        self._backfill_partner_from_reference()
        self.action_apply_model()

    def _backfill_partner_from_reference(self):
        """Fill in partner_id from the linked record when the call had no
        matched contact at the time it was created (manual contact-creation
        mode). Never overrides a partner that is already set."""
        for record in self:
            if not record.partner_id and record.model_reference and 'partner_id' in record.model_reference._fields:
                linked_partner = record.model_reference.partner_id
                if linked_partner:
                    record.partner_id = linked_partner.id

    @api.model
    def update_call_model(self, id, model_name, record_id, context=False, receive_model=False, receive_record=False):
        record = self.browse(id)
        if not context:
            if model_name and record_id:
                record.model_reference = '%s,%s' % (model_name, record_id) if model_name in self.env[
                    'ziwo.active.form'].sudo().search([]).mapped('model_id.model') else False
                record._backfill_partner_from_reference()
        else:
            active_history_bool = self.env.company.forge_ziwo_active_form_history
            if active_history_bool and receive_model:
                record.model_reference = '%s,%s' % (receive_model, receive_record) if receive_model in self.env[
                    'ziwo.active.form'].sudo().search([]).mapped('model_id.model') else False
                record._backfill_partner_from_reference()
            else:
                active_form_id = self.env.company.forge_ziwo_active_form_id.id
                if active_form_id:
                    if self.env['ziwo.active.form'].sudo().search_count([('id', '=', int(active_form_id))]) > 0:
                        active_form = self.env['ziwo.active.form'].sudo().browse(int(active_form_id))
                        if active_form.action == 'new' and active_form.model_id.model != 'res.partner':
                            contact_label = record.partner_id.name or record.mobile or 'New Contact'
                            default_inputs = {
                                'default_partner_id': record.partner_id.id,
                                'default_phone': record.mobile if not record.partner_id else False,
                                'default_user_id': self.env.user.id,
                                'default_team_id': self.env.user.sale_team_id.id,
                                'ziwo_model': 'ziwo.history',
                                'ziwo_record': record.id,
                            }
                            name = "%s's %s" % (contact_label, active_form.model_id.name)
                            sub_view_id = False

                            required_fields = self.env['ir.model.fields'].sudo().search(
                                [('model_id', '=', active_form.model_id.id), ('required', '=', True)])

                            action = {
                                'name': name,
                                'type': 'ir.actions.act_window',
                                'res_model': active_form.model_id.model,
                                'view_mode': 'form',
                                'view_id': sub_view_id,
                                'context': default_inputs,
                                'target': 'new',
                            }

                            return {
                                'record_id': record.id,
                                'action': action,
                            }

                        elif active_form.action == 'existing' and active_form.model_id.model == 'res.partner' and record.partner_id:
                            record.model_reference = '%s,%s' % (active_form.model_id.model, record.partner_id.id)
        return record.id

    @api.model
    def create_call_message(self, id):
        record = self.browse(id)
        record.create_message()
        if record.model_reference:
            record.action_apply_model()
        return record.id

    def send_to_agent(self):
        company = self.env.company
        navigate_enabled = (
            company.forge_ziwo_navigate_inbound_calls
            if self.call_type == 'inbound'
            else company.forge_ziwo_navigate_outbound_calls
        )
        if navigate_enabled:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Agent Screen',
                'res_model': 'agent.screen',
                'view_mode': 'form',
                'target': 'current',
                'context': {'default_partner_id': self.partner_id.id,
                            'default_ziwo_history_id': self.id,
                            'default_unmatched_mobile': self.mobile if not self.partner_id else False,
                            'form_view_initial_mode': 'edit',
                            'no_breadcrumbs': True},
            }

    @api.model
    def set_agent_screen(self, id):
        record = self.browse(id)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Agent Screen',
            'res_model': 'agent.screen',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_partner_id': record.partner_id.id,
                        'default_ziwo_history_id': record.id,
                        'default_unmatched_mobile': record.mobile if not record.partner_id else False,
                        'form_view_initial_mode': 'edit',
                        'no_breadcrumbs': True},
        }

    def action_add_note(self):
        return {
            "name": "Add Note",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "target": "new",
            "res_model": "add.note.wizard",
            "context": {"default_ziwo_history_id": self.id},
        }

    def action_view_call(self):
        return {
            "name": "View Call",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "views": [[False, "form"]],
            "target": "current",
            "res_model": "ziwo.history",
            "res_id": self.id
        }
