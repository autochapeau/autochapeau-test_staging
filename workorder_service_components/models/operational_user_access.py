from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, ValidationError


_GROUPS = {
    "operational_material_preparer": "workorder_service_components.group_workshop_material_preparer",
    "operational_quality_reviewer": "work_orders.group_quality_officer",
    "operational_edit_salesperson": "sale_salesperson_access.group_edit_salesperson",
}


class Users(models.Model):
    _inherit = "res.users"

    operational_material_preparer = fields.Boolean(
        string="تجهيز خامات الورشة", groups="base.group_system",
        compute="_compute_operational_access", inverse="_inverse_operational_material_preparer",
    )
    operational_quality_reviewer = fields.Boolean(
        string="مراجعة جودة المهام", groups="base.group_system",
        compute="_compute_operational_access", inverse="_inverse_operational_quality_reviewer",
    )
    operational_edit_salesperson = fields.Boolean(
        string="تغيير مندوب البيع", groups="base.group_system",
        compute="_compute_operational_access", inverse="_inverse_operational_edit_salesperson",
    )
    operational_salesperson_permission_available = fields.Boolean(
        compute="_compute_operational_access", groups="base.group_system",
    )

    @api.depends("groups_id")
    def _compute_operational_access(self):
        groups = {name: self.env.ref(xmlid, raise_if_not_found=False) for name, xmlid in _GROUPS.items()}
        for user in self:
            for name, group in groups.items():
                user[name] = bool(group and group in user.groups_id)
            user.operational_salesperson_permission_available = bool(groups["operational_edit_salesperson"])

    def _inverse_operational_material_preparer(self):
        self._save_operational_access("operational_material_preparer")

    def _inverse_operational_quality_reviewer(self):
        self._save_operational_access("operational_quality_reviewer")

    def _inverse_operational_edit_salesperson(self):
        self._save_operational_access("operational_edit_salesperson")

    def _save_operational_access(self, name):
        if not (self.env.su or self.env.user.has_group("base.group_system")):
            raise AccessError("تعديل صلاحيات التشغيل متاح لمسؤول إعدادات أودو بس.")
        group = self.env.ref(_GROUPS[name], raise_if_not_found=False)
        if not group:
            raise ValidationError("الصلاحية دي مش متاحة لأن التطبيق المرتبط بيها مش متسطّب.")
        for user in self:
            enabled = user[name]
            if enabled and user.share:
                raise ValidationError("صلاحيات التشغيل دي متاحة للحسابات الداخلية بس.")
            if enabled == (group in user.groups_id):
                continue
            command = Command.link(group.id) if enabled else Command.unlink(group.id)
            user.write({"groups_id": [command]})
            if enabled != (group in user.groups_id):
                raise ValidationError("الحساب واخد الصلاحية دي من مجموعة تانية. راجع المجموعات المرتبطة بيه الأول.")

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type != "form" or not arch.xpath("//page[@name='operational_access']"):
            return arch, view

        # Keep Odoo's generated fields in the form for implied group handling.
        # Only hide individual duplicates. Shared selection fields and the
        # groups_id fallback during upgrades still manage other permissions.
        for xmlid in _GROUPS.values():
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                for field in arch.xpath("//page[@name='access_rights']//field[@name=$name]", name=f"in_group_{group.id}"):
                    field.set("invisible", "1")
        return arch, view
