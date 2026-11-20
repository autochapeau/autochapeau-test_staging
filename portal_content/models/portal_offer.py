from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PortalOffer(models.Model):
    _name = "portal.offer"
    _inherit = "image.mixin"
    _description = "Portal Offer"

    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
    is_main = fields.Boolean(
        string="Main Offer",
        default=False,
        help="Only one offer can be marked as the main offer.",
    )

    def init(self):
        # Fix existing duplicates before creating the unique index
        self.env.cr.execute(
            """
            WITH keep AS (
                SELECT id
                FROM portal_offer
                WHERE is_main = true
                ORDER BY write_date DESC NULLS LAST, id DESC
                LIMIT 1
            )
            UPDATE portal_offer
               SET is_main = false
             WHERE is_main = true
               AND id NOT IN (SELECT id FROM keep)
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS portal_offer_unique_main
                ON portal_offer (is_main)
             WHERE is_main = true
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get("is_main") for vals in vals_list):
            last_main_idx = max(
                i for i, vals in enumerate(vals_list) if vals.get("is_main")
            )
            for i, vals in enumerate(vals_list):
                if i != last_main_idx and vals.get("is_main"):
                    vals["is_main"] = False
            # Clear existing main offers before insert (constrains run on create)
            self.search([("is_main", "=", True)]).with_context(
                skip_main_offer_check=True
            ).write({"is_main": False})
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("skip_main_offer_check"):
            return super().write(vals)

        if vals.get("is_main"):
            keep = self[-1]
            others = self.search([("is_main", "=", True), ("id", "!=", keep.id)])
            if others:
                others.with_context(skip_main_offer_check=True).write({"is_main": False})
            if len(self) > 1:
                other_in_self = self - keep
                if other_in_self:
                    other_in_self.with_context(skip_main_offer_check=True).write(
                        dict(vals, is_main=False)
                    )
                return keep.with_context(skip_main_offer_check=True).write(vals)

        return super().write(vals)

    @api.constrains("is_main")
    def _check_only_one_main_offer(self):
        if self.search_count([("is_main", "=", True)]) > 1:
            raise ValidationError(_("Only one offer can be marked as Main Offer."))
