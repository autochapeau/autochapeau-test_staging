from odoo import _, fields, models
from odoo.exceptions import UserError


class CarWorkorderService(models.Model):
    _inherit = "car.workorder.service"

    state = fields.Selection(
        selection_add=[
            ("quality", "Check Quality"),
            ("done",),
            ("cancel",),
        ],
        ondelete={"quality": "set default"},
    )
    qa_check_item_ids = fields.One2many(
        "workorder.service.qa.check.item",
        "service_id",
        string="Quality List",
        copy=False,
    )
    qa_fault_ids = fields.One2many(
        "workorder.service.qa.fault",
        "service_id",
        string="QA Faults",
        copy=False,
    )
    qa_fault_count = fields.Integer(
        string="QA Fault Count",
        compute="_compute_qa_fault_count",
    )
    qa_refuse_reason = fields.Text(
        string="QA Refusal Reason",
        readonly=True,
        copy=False,
    )
    qa_refuse_fault_type = fields.Selection(
        [
            ("simple", "Simple Fix"),
            ("technician", "Technician Fault"),
            ("supplier", "Supplier / Product Fault"),
        ],
        string="Last QA Refusal Type",
        readonly=True,
        copy=False,
    )

    def _compute_qa_fault_count(self):
        for service in self:
            service.qa_fault_count = len(service.qa_fault_ids)

    def _get_product_features(self):
        """Return product.feature records configured on the service product."""
        self.ensure_one()
        product = self.product_id
        if not product:
            return self.env["product.feature"]
        return product.product_tmpl_id.feature_ids

    def _get_service_boms(self):
        """Return car.bom lines configured on the service product."""
        self.ensure_one()
        if not self.product_id:
            return self.env["car.bom"]
        return self.product_id.bom_ids

    def _has_quality_checklist(self):
        self.ensure_one()
        return bool(self._get_product_features() or self._get_service_boms())

    def _ensure_qa_items(self):
        """Build quality checklist from Features + service BOM (add missing lines)."""
        CheckItem = self.env["workorder.service.qa.check.item"].sudo()
        for service in self:
            existing_feature_ids = set(
                service.qa_check_item_ids.filtered("feature_id").mapped("feature_id").ids
            )
            existing_bom_ids = set(
                service.qa_check_item_ids.filtered("bom_id").mapped("bom_id").ids
            )
            vals_list = []

            for feature in service._get_product_features():
                if feature.id in existing_feature_ids:
                    continue
                vals_list.append({
                    "service_id": service.id,
                    "item_type": "feature",
                    "feature_id": feature.id,
                    "name": feature.name,
                    "checked": False,
                })

            for bom in service._get_service_boms():
                if bom.id in existing_bom_ids:
                    continue
                product = bom.product_id
                qty = bom.quantity or 1.0
                unit_cost = product.standard_price if product else 0.0
                vals_list.append({
                    "service_id": service.id,
                    "item_type": "bom",
                    "bom_id": bom.id,
                    "product_id": product.id if product else False,
                    "quantity": qty,
                    "unit_cost": unit_cost,
                    "name": product.display_name if product else _("BOM item"),
                    "checked": False,
                })

            if vals_list:
                CheckItem.create(vals_list)

    # Keep old name as alias for any external callers.
    def _ensure_feature_qa_items(self):
        return self._ensure_qa_items()

    def action_finish(self):
        """Finish work: close time logs, then enter quality (or done if nothing to check)."""
        self.ensure_one()
        if self.state != "progress":
            raise UserError(_("You can only finish a task that is in progress."))

        has_checklist = self._has_quality_checklist()
        # Close timing / set date_end via parent (lands on done).
        super().action_finish()

        if not has_checklist:
            return True

        self._ensure_qa_items()
        self.state = "quality"
        self.message_post(body=_("Work finished. Waiting for quality check."))
        return True

    def action_confirm_quality(self):
        self.ensure_one()
        if self.state != "quality":
            raise UserError(_("You can only confirm quality while in Check Quality."))

        unchecked = self.qa_check_item_ids.filtered(lambda line: not line.checked)
        if unchecked:
            raise UserError(
                _("Please check all quality items before confirming:\n- %s")
                % "\n- ".join(unchecked.mapped("name"))
            )

        self.state = "done"
        self.qa_refuse_reason = False
        self.qa_refuse_fault_type = False
        self.message_post(body=_("Quality check confirmed. Task finished."))
        return True

    def action_refuse_quality(self):
        self.ensure_one()
        if self.state != "quality":
            raise UserError(_("You can only refuse quality while in Check Quality."))
        # Ensure BOM lines exist (e.g. after module upgrade on open quality tasks).
        self._ensure_qa_items()
        return {
            "type": "ir.actions.act_window",
            "name": _("Refuse Quality"),
            "res_model": "task.quality.refuse.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_service_id": self.id,
                "active_id": self.id,
                "active_model": "car.workorder.service",
            },
        }

    def action_apply_quality_refuse(
        self,
        reason,
        fault_type="simple",
        bom_item_ids=None,
        employee_id=False,
        partner_id=False,
    ):
        """Send task back to waiting; log reportable faults for technician/supplier."""
        self.ensure_one()
        reason = (reason or "").strip()
        if not reason:
            raise UserError(_("Please provide a refusal reason."))
        if self.state != "quality":
            raise UserError(_("You can only refuse quality while in Check Quality."))
        if fault_type not in ("simple", "technician", "supplier"):
            raise UserError(_("Invalid refusal type."))

        bom_items = bom_item_ids or self.env["workorder.service.qa.check.item"]
        if fault_type in ("technician", "supplier"):
            if not bom_items:
                raise UserError(
                    _("Please select at least one BOM part where the fault was found.")
                )
            invalid = bom_items.filtered(
                lambda i: i.service_id != self or i.item_type != "bom"
            )
            if invalid:
                raise UserError(_("Selected QA items must be BOM lines of this task."))
            if fault_type == "technician" and not employee_id:
                raise UserError(_("Please select the responsible technician."))

        # Reset checks while still in quality (write guard allows quality only).
        self.qa_check_item_ids.write({"checked": False})

        fault_vals_list = []
        if fault_type in ("technician", "supplier"):
            for item in bom_items:
                product = item.product_id
                if not product:
                    raise UserError(
                        _("BOM check item '%s' has no product.") % item.name
                    )
                fault_vals_list.append({
                    "service_id": self.id,
                    "fault_type": fault_type,
                    "reason": reason,
                    "qa_check_item_id": item.id,
                    "bom_id": item.bom_id.id if item.bom_id else False,
                    "product_id": product.id,
                    "quantity": item.quantity or 1.0,
                    "unit_cost": item.unit_cost
                    if item.unit_cost is not None
                    else product.standard_price,
                    "employee_id": employee_id if fault_type == "technician" else False,
                    "partner_id": partner_id if fault_type == "supplier" else False,
                    "refuse_date": fields.Datetime.now(),
                })

        if fault_vals_list:
            faults = self.env["workorder.service.qa.fault"].sudo().create(fault_vals_list)
            picking = faults._create_replacement_delivery()
            if picking:
                body_extra = _("<br/>Replacement delivery created: %s") % picking.name
            else:
                body_extra = ""
        else:
            picking = False
            body_extra = ""

        type_labels = {
            "simple": _("Simple Fix"),
            "technician": _("Technician Fault"),
            "supplier": _("Supplier / Product Fault"),
        }
        parts = ", ".join(bom_items.mapped("name")) if bom_items else ""
        body = _(
            "Quality refused.<br/>Type: %s<br/>Reason: %s"
        ) % (type_labels.get(fault_type, fault_type), reason)
        if parts:
            body += _("<br/>Faulty BOM part(s): %s") % parts
        body += body_extra

        self.write({
            "state": "waiting",
            "date_end": False,
            "qa_refuse_reason": reason,
            "qa_refuse_fault_type": fault_type,
        })
        self.message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
        return True

    def action_view_qa_faults(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("QA Faults"),
            "res_model": "workorder.service.qa.fault",
            "view_mode": "tree,form,pivot,graph",
            "domain": [("service_id", "=", self.id)],
            "context": {"default_service_id": self.id},
        }
