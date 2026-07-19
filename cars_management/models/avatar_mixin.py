from base64 import b64encode

from odoo import models
from odoo.tools import file_open


class AvatarMixinBlackDefault(models.AbstractModel):
    _inherit = "avatar.mixin"

    def _get_black_avatar(self):
        with file_open("cars_management/static/src/img/avatar_profile.png", "rb") as f:
            return b64encode(f.read())

    def _compute_avatar(self, avatar_field, image_field):
        result = super()._compute_avatar(avatar_field, image_field)
        for record in self:
            avatar = record[image_field]
            if not avatar:
                avatar = self._get_black_avatar()
            record[avatar_field] = avatar
        return result
