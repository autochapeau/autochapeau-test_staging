from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PortalHomeSlider(models.Model):
    _name = "portal.home.slider"
    _inherit = "image.mixin"
    _description = "Portal Home Slider"
    _order = "sequence, id"

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    first_title = fields.Char(translate=True)
    second_title = fields.Char(translate=True)
    url = fields.Char()
    image_ar = fields.Image(string="Arabic Image", max_width=1920, max_height=1920)
    image_en = fields.Image(string="English Image", max_width=1920, max_height=1920)
    overlay_opacity = fields.Float(
        string="Image Overlay", default=0.0,
        help="0 shows the original image; 1 applies the full dark overlay.",
    )

    @api.constrains("overlay_opacity")
    def _check_overlay_opacity(self):
        for slide in self:
            if not 0 <= slide.overlay_opacity <= 1:
                raise ValidationError(_("Image overlay must be between 0 and 1."))
