from odoo import api, fields, models, Command, _
from odoo.exceptions import AccessError, ValidationError


class Users(models.Model):
    _inherit = 'res.users'

    commission_access_role = fields.Selection([
        ('none', 'No commission access'),
        ('user', 'Salesperson — own commissions'),
        ('manager', 'Region manager — assigned teams'),
        ('admin', 'Commission administrator'),
    ], string='Commission role', compute='_compute_commission_access', inverse='_inverse_commission_access_role',
        groups='base.group_system', required=True)
    commission_region_ids = fields.Many2many('crm.team', string='Managed regions / teams',
        compute='_compute_commission_regions', inverse='_inverse_commission_regions', groups='base.group_system',
        help='A team has one commission manager. Selecting a team assigned to someone else transfers its management scope to this user, including its descendants.')
    commission_can_book_accruals = fields.Boolean(string='Historical accrual booking', compute='_compute_commission_access', groups='base.group_system')

    @api.depends('groups_id')
    def _compute_commission_access(self):
        groups = {role: self.env.ref('sales_region_commission.group_' + role) for role in ('user', 'manager', 'admin')}
        accountant = self.env.ref('account.group_account_manager')
        for user in self:
            user.commission_access_role = next((role for role in ('admin', 'manager', 'user') if groups[role] in user.groups_id), 'none')
            user.commission_can_book_accruals = groups['admin'] in user.groups_id and accountant in user.groups_id

    def _inverse_commission_access_role(self):
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only system administrators can assign commission access.'))
        groups = {role: self.env.ref('sales_region_commission.group_' + role) for role in ('user', 'manager', 'admin')}
        for user in self:
            role = user.commission_access_role
            commands = [Command.unlink(group.id) for group in groups.values()]
            if role != 'none':
                commands.append(Command.link(groups[role].id))
            user.write({'groups_id': commands})
            user._compute_commission_access()
            if user.commission_access_role != role:
                raise ValidationError(_('Another assigned group grants a higher commission role. Review inherited group permissions first.'))

    @api.depends('commission_managed_team_ids')
    def _compute_commission_regions(self):
        for user in self:
            user.commission_region_ids = user.commission_managed_team_ids

    def _inverse_commission_regions(self):
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only system administrators can assign managed regions from the user form.'))
        for user in self:
            chosen = user.commission_region_ids
            if any(not team.company_id or team.company_id not in user.company_ids or team.company_id not in self.env.companies for team in chosen):
                raise ValidationError(_('Managed regions must belong to a company allowed for both this user and the administrator.'))
            current = user.commission_managed_team_ids
            # System administrators already control user roles; restrict sudo to
            # the explicit, company-validated manager assignment on these teams.
            (current - chosen).sudo().write({'commission_manager_id': False})
            (chosen - current).sudo().write({'commission_manager_id': user.id})
