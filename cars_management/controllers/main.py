from odoo import _

from odoo.addons.im_livechat.controllers.main import LivechatController as BaseLivechatController


class LivechatController(BaseLivechatController):
    def _get_guest_name(self):
        return _("AutoChapeau Live Support")
