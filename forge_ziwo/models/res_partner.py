from odoo import models, fields, api, _
from datetime import timedelta
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    subscription_ids = fields.One2many(comodel_name="sale.order", inverse_name="partner_id", string="Sales Orders")
    task_ids = fields.One2many(comodel_name="project.task", inverse_name="partner_id", string="Tasks")
    calls_ids = fields.One2many(comodel_name="ziwo.history", inverse_name="partner_id", string="Calls")
    mobile = fields.Char(tracking=True)
    
    phone_trim = fields.Char(compute="_trim_number", store=True)
    mobile_trim = fields.Char(compute="_trim_number", store=True)

    #add constrains to make number unique
    @api.constrains('phone_trim', 'mobile_trim')
    def _check_unique_number(self):
        for record in self:
            if record.phone_trim:
                if self.env['res.partner'].sudo().search_count(['|',('mobile_trim', '=', record.phone_trim), ('phone_trim', '=', record.phone_trim), ('active', '=', True)]) > 1:
                    # raise UserError(_("Phone number " + record.phone_trim + " must be unique"))
                    existing_partner = self.env['res.partner'].sudo().search(['|',('mobile_trim', '=', record.phone_trim), ('phone_trim', '=', record.phone_trim), ('active', '=', True), ('id', '!=', record.id)], limit=1)
                    raise UserError(_('Phone number must be unique: already used by "' + existing_partner.name + '" [' + str(existing_partner.id) + ']'))
            if record.mobile_trim:
                if self.env['res.partner'].sudo().search_count(['|',('mobile_trim', '=', record.mobile_trim), ('phone_trim', '=', record.mobile_trim), ('active', '=', True)]) > 1:
                    # raise UserError(_("Mobile number " + record.mobile_trim + " must be unique"))
                    existing_partner = self.env['res.partner'].sudo().search(['|',('mobile_trim', '=', record.mobile_trim), ('phone_trim', '=', record.mobile_trim), ('active', '=', True), ('id', '!=', record.id)], limit=1)
                    raise UserError(_('Mobile number must be unique: already used by "' + existing_partner.name + '" [' + str(existing_partner.id) + ']'))


    @api.depends('phone', 'mobile')
    def _trim_number(self):
        for record in self:
            record["phone_trim"] = record["phone"]
            record["mobile_trim"] = record["mobile"]
            if record["phone"]:
                record["phone_trim"] = record["phone"].replace(' ', '')
            if record["mobile"]:
                record["mobile_trim"] = record["mobile"].replace(' ', '')

    @api.model
    def create(self, vals):
        partner = super(ResPartner, self).create(vals)
        if not self.env.context.get('import_file'):
            numbers = [n for n in (partner.mobile_trim, partner.phone_trim) if n]
            if numbers:
                domain = [('partner_id', '=', False), ('mobile', 'in', numbers)]
                unmatched_calls = self.env['ziwo.history'].sudo().search(domain)
                if unmatched_calls:
                    unmatched_calls.write({'partner_id': partner.id})
        return partner

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            name = name.split(' / ')[-1]
            domain = ['|', '|', '|', ('name', operator, name), ('phone_trim', operator, name), ('mobile_trim', operator, name), ('email', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    def open_create_call_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "create.call.wizard",
            "view_mode": "form",
            "view_type": "form",
            "target": "new",
            "context": {
                "default_model": 'res.partner',
                "default_record": self.id,
            },
        }
    
    def create_new_call(self):
        self.env['agent.screen'].sudo().create_new_call('res.partner', self.id, self.mobile_trim)
    
    def create_new_call_phone(self):
        self.env['agent.screen'].sudo().create_new_call('res.partner', self.id, self.phone_trim)
