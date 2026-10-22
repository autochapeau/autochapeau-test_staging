from odoo import models, fields

class ZiwoActiveForm(models.Model):
    _name = 'ziwo.active.form'
    _description = 'Ziwo Active Form'

    model_id = fields.Many2one('ir.model', string='Model', domain=[('model', 'in', ['res.partner', 'crm.lead', 'sale.order', 'project.task'])])
    name = fields.Char(string='Name', related='model_id.name', readonly=True)
    active = fields.Boolean(string='Active', default=False)
    action = fields.Selection(selection=[('new', 'New'), ('existing', 'Existing')], string='Action')
