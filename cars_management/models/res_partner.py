from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.osv import expression


class ResPartner(models.Model):
    _inherit = "res.partner"

    partner_type = fields.Selection(
        [("internal", _("Internal")), ("external", _("External"))], default="external")
    source_id = fields.Many2one("utm.source")
    vehicle_ids = fields.One2many("fleet.vehicle", "partner_id", string="Cars")
    cars_count = fields.Integer(compute="_compute_cars_count")
    birthdate = fields.Date()
    name = fields.Char(translate=True)
    membership_id = fields.Many2one(
        "customer.membership.level",
        string="Membership",
        compute="_compute_membership_id",
        help="Membership level computed from the customer's total invoiced amount.",
    )

    membership_badge = fields.Html(
        string="Membership Badge",
        compute="_compute_membership_badge",
        sanitize=False,
    )

    @api.depends("total_invoiced")
    def _compute_membership_id(self):
        Membership = self.env["customer.membership.level"]
        for partner in self:
            amount = partner.total_invoiced or 0.0
            partner.membership_id = Membership.search(
                [("amount_from", "<=", amount), ("amount_to", ">=", amount)],
                limit=1,
            )

    @api.depends("membership_id")
    def _compute_membership_badge(self):
        # same style for every membership level.
        template = Markup(
            '<span class="badge rounded-pill text-bg-primary fs-6">{}</span>'
        )
        for partner in self:
            membership = partner.membership_id
            partner.membership_badge = (
                template.format(membership.name) if membership else False
            )

    def _compute_cars_count(self):
        for partner in self:
            partner.cars_count = len(partner.vehicle_ids)

    def action_open_cars(self):
        self.ensure_one()
        return {
            "name": _("Related Cars"),
            "type": "ir.actions.act_window",
            "res_model": "fleet.vehicle",
            "view_mode": "list",
            "domain": [("partner_id", "=", self.id)],
        }

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)

        if view_type == "form":
            for node in arch.xpath("//field[@name='name']"):
                if "widget" in node.attrib:
                    del node.attrib["widget"]
        return arch, view

    @api.depends("complete_name", "email", "vat", "state_id", "country_id", "commercial_company_name")
    @api.depends_context(
        "show_address", "partner_show_db_id", "address_inline",
        "show_email", "show_vat", "lang", "hide_company_name",
    )
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get("hide_company_name"):
            for partner in self:
                partner.display_name = partner.name or ""

    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name and operator in ('ilike', 'like', '=', '=like', '=ilike'):
            domain = expression.AND([
                domain,
                ['|', '|',
                    ('complete_name', operator, name),
                    ('phone', operator, name),
                    ('mobile', operator, name)],
            ])
            return self._search(domain, limit=limit, order=order)
        return super()._name_search(name, domain, operator, limit, order)
