from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TaskQualityRefuseWizard(models.TransientModel):
    _name = "task.quality.refuse.wizard"
    _description = "Task Quality Refuse Reason Wizard"

    service_id = fields.Many2one(
        "car.workorder.service",
        string="Task",
        required=True,
        ondelete="cascade",
    )
    fault_type = fields.Selection(
        [
            ("simple", "Simple Fix"),
            ("technician", "Technician Fault"),
            ("supplier", "Supplier / Product Fault"),
        ],
        string="Refusal Type",
        required=True,
        default="simple",
    )
    reason = fields.Text(string="Reason for Refusal", required=True)
    bom_item_ids = fields.Many2many(
        "workorder.service.qa.check.item",
        "task_quality_refuse_bom_rel",
        "wizard_id",
        "item_id",
        string="Faulty BOM Part(s)",
        domain="[('service_id', '=', service_id), ('item_type', '=', 'bom')]",
        help="Select the BOM part(s) where the fault was found. "
             "Cost in the report is based on these parts only.",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Responsible Technician",
        domain="[('id', 'in', available_employee_ids)]",
    )
    available_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_available_employee_ids",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        domain="[('supplier_rank', '>', 0)]",
        help="Optional supplier linked to this product fault.",
    )
    has_bom_items = fields.Boolean(compute="_compute_has_bom_items")

    @api.depends("service_id", "service_id.qa_check_item_ids", "service_id.qa_check_item_ids.item_type")
    def _compute_has_bom_items(self):
        for wizard in self:
            wizard.has_bom_items = bool(
                wizard.service_id.qa_check_item_ids.filtered(lambda i: i.item_type == "bom")
            )

    @api.depends("service_id", "service_id.staff_ids")
    def _compute_available_employee_ids(self):
        for wizard in self:
            wizard.available_employee_ids = wizard.service_id.staff_ids

    @api.onchange("service_id")
    def _onchange_service_id(self):
        if self.service_id and self.service_id.staff_ids:
            self.employee_id = self.service_id.staff_ids[:1]
        else:
            self.employee_id = False

    @api.onchange("fault_type")
    def _onchange_fault_type(self):
        if self.fault_type == "simple":
            self.bom_item_ids = False
            self.employee_id = False
            self.partner_id = False
        elif self.fault_type == "technician" and not self.employee_id:
            if self.service_id and self.service_id.staff_ids:
                self.employee_id = self.service_id.staff_ids[:1]
        elif self.fault_type == "supplier":
            self.employee_id = False

    @api.onchange("bom_item_ids", "fault_type")
    def _onchange_bom_item_ids_supplier(self):
        if self.fault_type != "supplier" or self.partner_id or not self.bom_item_ids:
            return
        # Prefer first seller of the first selected BOM product.
        for item in self.bom_item_ids:
            product = item.product_id
            if not product:
                continue
            sellers = product.seller_ids.filtered(lambda s: s.partner_id)
            if sellers:
                self.partner_id = sellers[0].partner_id
                break

    def action_confirm(self):
        self.ensure_one()
        if not self.service_id:
            raise UserError(_("No task found."))
        self.service_id.action_apply_quality_refuse(
            reason=self.reason,
            fault_type=self.fault_type,
            bom_item_ids=self.bom_item_ids,
            employee_id=self.employee_id.id if self.employee_id else False,
            partner_id=self.partner_id.id if self.partner_id else False,
        )
        return {"type": "ir.actions.act_window_close"}
