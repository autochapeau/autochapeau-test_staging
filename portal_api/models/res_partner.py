import werkzeug.urls

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_signup_url_for_action(self, url=None, action=None, view_type=None, menu_id=None, res_id=None, model=None):
        res = super()._get_signup_url_for_action(url, action, view_type, menu_id, res_id, model)
        for partner in self:
            if partner.sudo().signup_type == "reset":
                portal_url = self.env["ir.config_parameter"].sudo().get_param("web.base.portal_url")
                query = {"token": partner.sudo().signup_token}
                res[partner.id] = f"{portal_url}/reset_password?{werkzeug.urls.url_encode(query)}"
        return res
