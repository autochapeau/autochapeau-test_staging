from odoo import models, fields, _
from odoo.exceptions import UserError


class QualityRefuseReasonWizard(models.TransientModel):
    _name = 'quality.refuse.reason.wizard'
    _description = 'Quality Refuse Reason Wizard'

    reason = fields.Text(string='Reason for Refusal', required=True)

    def action_confirm(self):
        self.ensure_one()
        active_id = self.env.context.get('active_id')
        work_order = self.env['car.work.order'].browse(active_id)
        if not work_order:
            raise UserError(_('No work order found.'))
        # Save the reason on the work order
        work_order.refuse_reason = self.reason
        work_order.state = 'progress'
        # Log note
        work_order.message_post(
            body=_('QA Refusal Reason: %s') % self.reason,
            message_type='comment',
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}
