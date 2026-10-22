from odoo import models, fields, api
from datetime import timedelta


class AgentScreen(models.TransientModel):
    _name = "agent.screen"
    _description = "Agent Screen"

    name = fields.Char(default="Agent Screen")

    partner_id = fields.Many2one("res.partner", string="Contact")
    ziwo_history_id = fields.Many2one("ziwo.history", string="Call")
    unmatched_mobile = fields.Char(string="Caller Number")

    phone = fields.Char(string="Phone", related="partner_id.phone")
    mobile = fields.Char(string="Mobile", related="partner_id.mobile")
    email = fields.Char(string="Email", related="partner_id.email")
    company = fields.Char(string="Company", related="partner_id.parent_id.name")
    country = fields.Char(string="Country", related="partner_id.country_id.name")
    tz = fields.Selection(string="Timezone", related="partner_id.tz")
    tz_offset = fields.Char(string="Timezone", related="partner_id.tz_offset")

    show_company_filter = fields.Boolean(string="Show Company Filter", compute="_compute_show_company_filter", readonly=True)
    enable_company_filter = fields.Boolean(string="Enable Company Filter", default=False, readonly=True)
    @api.depends('partner_id')
    def _compute_show_company_filter(self):
        for record in self:
            record["show_company_filter"] = True if record.partner_id.parent_id else False
    def toggle_commpany_filter(self):
        self.ensure_one()
        if self.enable_company_filter:
            self.enable_company_filter = False
        else:
            self.enable_company_filter = True
    
    opportunity_ids = fields.Many2many(
        comodel_name='crm.lead',
        string='Opportunities',
        compute='_compute_many2many',
    )
    subscription_ids = fields.Many2many(
        comodel_name='sale.order',
        string='Sales Orders',
        compute='_compute_many2many',
    )
    task_ids = fields.Many2many(
        comodel_name='project.task',
        string='Tasks',
        compute='_compute_many2many',
    )
    calls_ids = fields.Many2many(
        comodel_name='ziwo.history',
        string='Calls',
        compute='_compute_many2many',
    )

    @api.depends('partner_id', 'show_company_filter', 'enable_company_filter')
    def _compute_many2many(self):
        for record in self:
            record["subscription_ids"] = record["task_ids"] = record["calls_ids"] = record["opportunity_ids"] = [(6, 0, [])]
            if record.partner_id:
                domain = [('company_id', '=', self.env.user.company_id.id)]
                if record.show_company_filter and record.enable_company_filter:
                    domain.append(('partner_parent', '=', record.partner_id.parent_id.id))
                else:
                    if record.partner_id.is_company:
                        domain.append(('partner_parent', '=', record.partner_id.id))
                    else:
                        domain.append(('partner_id', '=', record.partner_id.id))
                record["subscription_ids"] = self.env["sale.order"].sudo().search(domain)
                record["task_ids"] = self.env["project.task"].sudo().search(domain)
                record["calls_ids"] = self.env["ziwo.history"].sudo().search(domain)
                record["opportunity_ids"] = self.env["crm.lead"].sudo().search(domain)


    opportunity_count = fields.Integer(string='Total:', compute='_compute_count')
    subscription_count = fields.Integer(string='Total:', compute='_compute_count')
    task_count = fields.Integer(string='Total:', compute='_compute_count')
    calls_count = fields.Integer(string='Total:', compute='_compute_count')

    @api.depends('opportunity_ids', 'subscription_ids', 'task_ids', 'calls_ids')
    def _compute_count(self):
        for record in self:
            record["opportunity_count"] = len(record["opportunity_ids"]) if record.opportunity_ids else 0
            record["subscription_count"] = len(record["subscription_ids"]) if record.subscription_ids else 0
            record["task_count"] = len(record["task_ids"]) if record.task_ids else 0
            record["calls_count"] = len(record["calls_ids"]) if record.calls_ids else 0

    show_oppotunity_tab = fields.Boolean(
        string="Show Opportunity",
        default=lambda self: 'crm.lead' in self.env['ziwo.active.form'].sudo().search([]).mapped('model_id.model')
    )
    show_subscription_tab = fields.Boolean(
        string="Show Sales Orders",
        default=lambda self: 'sale.order' in self.env['ziwo.active.form'].sudo().search([]).mapped('model_id.model')
    )
    show_task_tab = fields.Boolean(
        string="Show Task",
        default=lambda self: 'project.task' in self.env['ziwo.active.form'].sudo().search([]).mapped('model_id.model')
    )

    def open_edit_contact_wizard(self):
        self.ensure_one()
        wizard = self.env["edit.contact.wizard"].sudo().create({
            "partner_id": self.partner_id.id,
            "ziwo_history_id": self.ziwo_history_id.id,
            "create_mobile": self.unmatched_mobile,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "edit.contact.wizard",
            "view_mode": "form",
            "view_type": "form",
            "res_id": wizard.id,
            "target": "new",
        }

    def create_new_opportunity(self):
        self.env['agent.screen'].sudo().update_call_model('crm.lead')
        return {
            'name': 'Create New Opportunity',
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_phone': self.unmatched_mobile if not self.partner_id else False,
                'default_user_ids': self.env.user.id,
                'default_team_id': self.env.user.sale_team_id.id,
            },
            'target': 'current',
        }

    def create_new_subscription(self):
        self.env['agent.screen'].sudo().update_call_model('sale.order')
        return {
            'name': 'Create New Sale Order',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_phone': self.unmatched_mobile if not self.partner_id else False,
                'default_user_id': self.env.user.id,
                'default_team_id': self.env.user.sale_team_id.id,
            },
            'target': 'current',
        }

    def create_new_task(self):
        self.env['agent.screen'].sudo().update_call_model('project.task')
        return {
            'name': 'Create New Task',
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_phone': self.unmatched_mobile if not self.partner_id else False,
                'default_user_ids': [(6, 0, [self.env.user.id])],
                'default_team_id': self.env.user.sale_team_id.id,
            },
            'target': 'current',
        }

    def create_new_call(self, model=False, record=False, mobile=False):
        message = {
            'action': 'call',
            'mobile': mobile or self.partner_id.mobile_trim or self.unmatched_mobile,
            'model': model,
            'record': record,
        }
        self.env['bus.bus'].sudo()._sendone(self.env.user.partner_id,'ziwo/bus', message)

    def create_new_call_phone(self, model=False, record=False, phone=False):
        message = {
            'action': 'call',
            'mobile': phone or self.partner_id.phone_trim or self.unmatched_mobile,
            'model': model,
            'record': record,
        }
        self.env['bus.bus'].sudo()._sendone(self.env.user.partner_id,'ziwo/bus', message)
        
    def update_call_model(self, model='agent.screen', record=False):
        message = {
            'action': 'update',
            'model': model,
            'record': record,
        }
        self.env['bus.bus'].sudo()._sendone(self.env.user.partner_id,'ziwo/bus', message)
        