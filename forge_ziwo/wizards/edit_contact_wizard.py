from odoo import models, fields

class EditContactWizard(models.TransientModel):
    _name = "edit.contact.wizard"
    _description = "Edit Contact Wizard"

    partner_id = fields.Many2one("res.partner", string="Contact")
    ziwo_history_id = fields.Many2one("ziwo.history", string="Call")

    # CHANGE FIELDS (existing contact) ====================

    change_name = fields.Char(string="Name", related="partner_id.name", readonly=False)
    change_phone = fields.Char(string="Phone", related="partner_id.phone", readonly=False)
    change_mobile = fields.Char(string="Mobile", related="partner_id.mobile", readonly=False)
    change_email = fields.Char(string="Email", related="partner_id.email", readonly=False)
    change_parent_id = fields.Many2one("res.partner", string="Company", related="partner_id.parent_id", readonly=False, domain="[('is_company', '=', True)]")

    # CREATE FIELDS (no contact linked yet) ====================

    create_name = fields.Char(string="Name")
    create_phone = fields.Char(string="Phone")
    create_mobile = fields.Char(string="Mobile")
    create_email = fields.Char(string="Email")
    create_parent_id = fields.Many2one("res.partner", string="Company", domain="[('is_company', '=', True)]")

    # CHANGE ACTION ====================

    def save_changes(self):
        self.ensure_one()
        if self.partner_id:
            values = {
                "name": self.change_name,
                "phone": self.change_phone,
                "mobile": self.change_mobile,
                "email": self.change_email,
                "parent_id": self.change_parent_id.id if self.change_parent_id else False,
            }
            self.partner_id.sudo().write(values)
        else:
            partner = self.env["res.partner"].sudo().create({
                "name": self.create_name or self.create_mobile or self.create_phone,
                "phone": self.create_phone,
                "mobile": self.create_mobile,
                "email": self.create_email,
                "parent_id": self.create_parent_id.id if self.create_parent_id else False,
            })
            self.partner_id = partner
            if self.ziwo_history_id and not self.ziwo_history_id.partner_id:
                self.ziwo_history_id.partner_id = partner
        if self.ziwo_history_id:
            return self.ziwo_history_id.set_agent_screen(self.ziwo_history_id.id)
        return {"type": "ir.actions.act_window_close"}

    def cancel(self):
        self.sudo().unlink()
        return {'type': 'ir.actions.act_window_close'}
