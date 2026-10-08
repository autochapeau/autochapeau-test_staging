from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare, float_is_zero


_QUALITY_FIELDS = frozenset({
    "fault_type",
    "quality_reason",
    "employee_id",
    "supplier_id",
    "technician_cost",
    "company_cost",
    "part_ids",
})


class MaintenanceClaim(models.Model):
    _name = "maintenance.claim"
    _description = "Maintenance Claim"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Reference", readonly=True, copy=False, default="New")
    state = fields.Selection(
        [
            ("quality", "Waiting for Quality"),
            ("confirmed", "Confirmed"),
            ("cancelled", "Cancelled"),
        ],
        default="quality",
        required=True,
        tracking=True,
        copy=False,
    )
    origin_sale_id = fields.Many2one(
        "sale.order",
        string="Original Order",
        required=True,
        ondelete="restrict",
        index=True,
        readonly=True,
    )
    origin_sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Original Service Line",
        required=True,
        ondelete="restrict",
        readonly=True,
    )
    service_product_id = fields.Many2one(
        "product.product",
        string="Service",
        related="origin_sale_line_id.product_id",
        store=True,
    )
    is_window_tinting = fields.Boolean(
        related="service_product_id.product_tmpl_id.is_window_tinting",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        related="origin_sale_id.partner_id",
        store=True,
    )
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Car",
        related="origin_sale_id.vehicle_id",
        store=True,
    )
    branch_id = fields.Many2one(
        "hr.department",
        string="Branch",
        related="origin_sale_id.branch_id",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="origin_sale_id.company_id",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
    )
    problem_location = fields.Text(string="Problem Location", required=True)

    fault_type = fields.Selection(
        [
            ("customer", "Customer Fault"),
            ("technician", "Technician Fault"),
            ("supplier", "Supplier / Product Fault"),
        ],
        string="Cause",
        tracking=True,
        copy=False,
    )
    quality_reason = fields.Text(string="Quality Notes", copy=False)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Technician",
        copy=False,
        domain="[('is_technician', '=', True), ('branch_id', '=', branch_id)]",
    )
    supplier_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        copy=False,
        domain="[('supplier_rank', '>', 0)]",
    )
    part_ids = fields.One2many(
        "maintenance.claim.part",
        "claim_id",
        string="Parts",
        copy=False,
    )
    charge_cost = fields.Monetary(
        string="Charge Cost",
        compute="_compute_charge_cost",
        currency_field="currency_id",
    )
    technician_cost = fields.Monetary(
        string="Charged to Technician",
        currency_field="currency_id",
        copy=False,
    )
    company_cost = fields.Monetary(
        string="Charged to Company",
        currency_field="currency_id",
        copy=False,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Maintenance Order",
        copy=False,
        readonly=True,
    )
    appointment_id = fields.Many2one(
        "car.appointment",
        string="Appointment",
        copy=False,
        readonly=True,
    )
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        copy=False,
        readonly=True,
    )

    @api.depends("part_ids.include", "part_ids.quantity", "part_ids.unit_cost")
    def _compute_charge_cost(self):
        for claim in self:
            claim.charge_cost = sum(
                (part.quantity or 0.0) * (part.unit_cost or 0.0)
                for part in claim.part_ids
                if part.include
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("maintenance.claim") or _("New")
                )
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and (_QUALITY_FIELDS & set(vals)):
            if not self.env.user.has_group("work_orders.group_quality_officer"):
                raise UserError(_("Only quality can set the maintenance cause."))
        if any(claim.state != "quality" for claim in self) and (_QUALITY_FIELDS & set(vals)):
            raise UserError(_("You cannot change the cause after the request is confirmed."))
        if "move_id" not in vals and any(claim.move_id for claim in self):
            locked = {"technician_cost", "company_cost", "employee_id", "supplier_id", "fault_type"}
            if locked & set(vals):
                raise UserError(_("You cannot change cost allocation after accounting is posted."))
        return super().write(vals)

    @api.constrains("origin_sale_id", "origin_sale_line_id")
    def _check_origin_line(self):
        for claim in self:
            line = claim.origin_sale_line_id
            if line.order_id != claim.origin_sale_id:
                raise ValidationError(_("The selected service does not belong to this order."))
            if line.display_type or line.product_id.detailed_type != "service":
                raise ValidationError(_("Maintenance can only be opened for a service line."))

    def _suggested_employee(self):
        self.ensure_one()
        services = self.origin_sale_id.appointment_ids.mapped(
            "car_work_order_id.service_ids"
        ).filtered(lambda service: service.product_id == self.service_product_id)
        staff = services.mapped("staff_ids").filtered("is_technician")
        if self.branch_id:
            branched = staff.filtered(lambda employee: employee.branch_id == self.branch_id)
            if branched:
                staff = branched
        return staff[:1]

    def _suggested_supplier(self):
        self.ensure_one()
        products = self.part_ids.filtered("include").mapped("product_id") or self.part_ids.mapped("product_id")
        for product in products:
            sellers = product.seller_ids.filtered(lambda seller: seller.partner_id)
            if sellers:
                return sellers[0].partner_id
        return self.env["res.partner"]

    @api.onchange("fault_type", "part_ids")
    def _onchange_fault_type(self):
        if self.fault_type == "technician":
            if not self.employee_id:
                self.employee_id = self._suggested_employee()
            self.technician_cost = self.charge_cost
            self.company_cost = 0.0
        elif self.fault_type == "supplier":
            if not self.supplier_id:
                self.supplier_id = self._suggested_supplier()
            self.technician_cost = 0.0
            self.company_cost = self.charge_cost
        else:
            self.technician_cost = 0.0
            self.company_cost = 0.0

    @api.onchange("technician_cost")
    def _onchange_technician_cost(self):
        if self.fault_type in ("technician", "supplier"):
            self.company_cost = (self.charge_cost or 0.0) - (self.technician_cost or 0.0)

    @api.onchange("company_cost")
    def _onchange_company_cost(self):
        if self.fault_type in ("technician", "supplier"):
            self.technician_cost = (self.charge_cost or 0.0) - (self.company_cost or 0.0)

    def _check_quality_user(self):
        if not self.env.user.has_group("work_orders.group_quality_officer"):
            raise UserError(_("Only quality can confirm the maintenance cause."))

    def _currency_rounding(self):
        self.ensure_one()
        return self.currency_id.rounding or 0.01

    def _validate_cause(self):
        self.ensure_one()
        if self.fault_type not in ("customer", "technician", "supplier"):
            raise UserError(_("Select who caused the problem."))
        if not (self.quality_reason or "").strip():
            raise UserError(_("Enter the quality notes."))
        if self.is_window_tinting:
            selected_glass = self.part_ids.filtered(
                lambda part: part.include and part.glass_type_id and part.tint_percentage_id
            )
            if not selected_glass:
                raise UserError(_("Select the glass that needs maintenance."))
        if self.fault_type == "customer":
            return
        if not self.part_ids.filtered("include"):
            raise UserError(_("Select at least one part to charge."))
        if float_compare(self.charge_cost, 0.0, precision_rounding=self._currency_rounding()) <= 0:
            raise UserError(_("The charge cost must be greater than zero. Set the part cost first."))
        if self.fault_type == "technician" and not (self.employee_id or self._suggested_employee()):
            raise UserError(_("Select the responsible technician."))
        if self.fault_type == "supplier" and not (self.supplier_id or self._suggested_supplier()):
            raise UserError(_("Select the supplier."))

    def _ensure_cost_split(self):
        self.ensure_one()
        rounding = self._currency_rounding()
        if self.fault_type == "customer":
            self.technician_cost = 0.0
            self.company_cost = 0.0
            return
        if not self.employee_id and self.fault_type == "technician":
            self.employee_id = self._suggested_employee()
        if not self.supplier_id and self.fault_type == "supplier":
            self.supplier_id = self._suggested_supplier()
        if self.fault_type == "technician" and not self.employee_id:
            raise UserError(_("Select the responsible technician."))
        if self.fault_type == "supplier" and not self.supplier_id:
            raise UserError(_("Select the supplier."))
        if float_is_zero(self.technician_cost, precision_rounding=rounding) and float_is_zero(
            self.company_cost, precision_rounding=rounding
        ):
            if self.fault_type == "technician":
                self.technician_cost = self.charge_cost
                self.company_cost = 0.0
            else:
                self.technician_cost = 0.0
                self.company_cost = self.charge_cost
        if float_compare(self.technician_cost, 0.0, precision_rounding=rounding) < 0:
            raise UserError(_("Charged to Technician cannot be negative."))
        if float_compare(self.company_cost, 0.0, precision_rounding=rounding) < 0:
            raise UserError(_("Charged to Company cannot be negative."))
        total = (self.technician_cost or 0.0) + (self.company_cost or 0.0)
        if float_compare(total, self.charge_cost, precision_rounding=rounding) != 0:
            raise UserError(_("Technician and company amounts must add up to the charge cost."))

    def _maintenance_customer(self):
        self.ensure_one()
        origin = self.origin_sale_id
        if origin.order_type == "contract" and origin.subordinate_id:
            return origin.subordinate_id
        return origin.partner_id

    def _create_maintenance_sale_order(self):
        """Confirmed internal order for the same service. Customer price is zero unless the customer is at fault."""
        self.ensure_one()
        origin = self.origin_sale_id
        if not origin.vehicle_id:
            raise UserError(_("The original order has no car."))
        customer = self._maintenance_customer()
        if not customer:
            raise UserError(_("The original order has no customer."))
        vals = {
            "partner_id": customer.id,
            "vehicle_id": origin.vehicle_id.id,
            "order_type": "intern",
            "company_id": origin.company_id.id,
            "user_id": origin.user_id.id or self.env.user.id,
            "origin": origin.name,
            "client_order_ref": self.name,
            "maintenance_claim_id": self.id,
        }
        if origin.branch_id:
            vals["branch_id"] = origin.branch_id.id
        if origin.pricelist_id:
            vals["pricelist_id"] = origin.pricelist_id.id
        if origin.warehouse_id:
            vals["warehouse_id"] = origin.warehouse_id.id
        if origin.team_id:
            vals["team_id"] = origin.team_id.id
        order = self.env["sale.order"].sudo().create(vals)
        line_vals = {
            "product_id": self.service_product_id.id,
            "product_uom_qty": 1.0,
        }
        no_variant = self.origin_sale_line_id.product_no_variant_attribute_value_ids
        if no_variant:
            line_vals["product_no_variant_attribute_value_ids"] = [Command.set(no_variant.ids)]
        order.sudo().write({"order_line": [Command.create(line_vals)]})
        self._copy_selected_tint_details(order)
        order.sudo().action_confirm()
        return order

    def _copy_selected_tint_details(self, order):
        """Keep only the glasses quality selected, not every glass from the original job."""
        self.ensure_one()
        if not self.is_window_tinting:
            return
        selected = self.part_ids.filtered(
            lambda part: part.include and part.glass_type_id and part.tint_percentage_id
        )
        if not selected:
            raise UserError(_("Select the glass that needs maintenance."))
        sale_line = order.order_line.filtered(
            lambda line: not line.display_type and line.product_id == self.service_product_id
        )[:1]
        if not sale_line:
            raise UserError(_("The maintenance order has no service line."))
        sale_line.sudo().write({
            "tint_detail_ids": [
                Command.create({
                    "sequence": part.origin_tint_detail_id.sequence or 10,
                    "glass_type_id": part.glass_type_id.id,
                    "tint_percentage_id": part.tint_percentage_id.id,
                    "note": part.origin_tint_detail_id.note or False,
                })
                for part in selected
            ],
        })

    def _get_accounts(self):
        self.ensure_one()
        company = self.company_id
        journal = company.qa_fault_journal_id
        tech_account = company.qa_fault_technician_account_id
        company_account = company.qa_fault_company_account_id
        offset_account = company.qa_fault_offset_account_id
        missing = []
        if not journal:
            missing.append(_("QA Fault Journal"))
        if not tech_account:
            missing.append(_("QA Fault Technician Account"))
        if not company_account:
            missing.append(_("QA Fault Company Expense Account"))
        if not offset_account:
            missing.append(_("QA Fault Offset Account"))
        if missing:
            raise UserError(
                _("Configure QA fault accounts in Settings → Accounting → Default Accounts:\n- %s")
                % "\n- ".join(missing)
            )
        return journal, tech_account, company_account, offset_account

    def _get_technician_partner(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            raise UserError(_("Select a technician before posting accounting."))
        partner = employee.work_contact_id or employee.user_id.partner_id
        if not partner:
            raise UserError(
                _("Employee '%s' has no work contact. Set it on the employee so the amount appears on the partner ledger.")
                % employee.display_name
            )
        if partner.customer_rank <= 0:
            partner.sudo().write({"customer_rank": 1})
        return partner

    def _post_accounting(self):
        self.ensure_one()
        if self.fault_type == "customer":
            return self.env["account.move"]
        journal, tech_account, company_account, offset_account = self._get_accounts()
        company = self.company_id
        currency = company.currency_id
        rounding = currency.rounding or 0.01
        tech_amt = self.technician_cost or 0.0
        company_amt = self.company_cost or 0.0
        if float_is_zero(tech_amt, precision_rounding=rounding) and float_is_zero(
            company_amt, precision_rounding=rounding
        ):
            raise UserError(_("Nothing to post: both charged amounts are zero."))
        total = currency.round(tech_amt + company_amt)
        label = self.name or _("Maintenance")
        analytic = False
        if self.branch_id and self.branch_id.analytic_account_id:
            analytic = {str(self.branch_id.analytic_account_id.id): 100}
        line_vals = []
        if not float_is_zero(tech_amt, precision_rounding=rounding):
            partner = self._get_technician_partner()
            receivable = partner.property_account_receivable_id
            account = tech_account
            if receivable and receivable.company_id == company:
                account = receivable
            line_vals.append(Command.create({
                "name": _("Technician share: %s") % label,
                "account_id": account.id,
                "partner_id": partner.id,
                "debit": currency.round(tech_amt),
                "credit": 0.0,
                "analytic_distribution": analytic,
            }))
        if not float_is_zero(company_amt, precision_rounding=rounding):
            line_vals.append(Command.create({
                "name": _("Company share: %s") % label,
                "account_id": company_account.id,
                "debit": currency.round(company_amt),
                "credit": 0.0,
                "analytic_distribution": analytic,
            }))
        line_vals.append(Command.create({
            "name": _("Maintenance offset: %s") % label,
            "account_id": offset_account.id,
            "debit": 0.0,
            "credit": total,
            "analytic_distribution": analytic,
        }))
        move = self.env["account.move"].sudo().create({
            "move_type": "entry",
            "journal_id": journal.id,
            "date": fields.Date.context_today(self),
            "ref": label,
            "company_id": company.id,
            "line_ids": line_vals,
        })
        move.action_post()
        return move

    def action_confirm_cause(self):
        """Quality decision: charge the right party, then open a maintenance order and its appointment."""
        self.ensure_one()
        self._check_quality_user()
        if self.state != "quality":
            raise UserError(_("This maintenance request is already processed."))
        self._validate_cause()
        self._ensure_cost_split()
        order = self._create_maintenance_sale_order()
        move = self._post_accounting()
        self.write({
            "state": "confirmed",
            "sale_order_id": order.id,
            "move_id": move.id if move else False,
        })
        cause = dict(self._fields["fault_type"].selection).get(self.fault_type, self.fault_type)
        self.origin_sale_id.sudo().message_post(body=_(
            "Maintenance %(claim)s confirmed. Cause: %(cause)s. Maintenance order: %(order)s.",
            claim=self.name,
            cause=cause,
            order=order.name,
        ))
        return order.action_create_appointment()

    def action_cancel(self):
        self.ensure_one()
        if self.state != "quality":
            raise UserError(_("Only a request that is still waiting for quality can be cancelled."))
        self.state = "cancelled"

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_("No maintenance order yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Maintenance Order"),
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": self.sale_order_id.id,
            "target": "current",
        }

    def action_open_appointment(self):
        self.ensure_one()
        if self.appointment_id:
            return {
                "type": "ir.actions.act_window",
                "name": _("Appointment"),
                "res_model": "car.appointment",
                "view_mode": "form",
                "res_id": self.appointment_id.id,
                "target": "current",
            }
        if not self.sale_order_id:
            raise UserError(_("Confirm the cause before creating the appointment."))
        return self.sale_order_id.action_create_appointment()

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("No journal entry is linked to this request."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entry"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.move_id.id,
            "target": "current",
        }


class MaintenanceClaimPart(models.Model):
    _name = "maintenance.claim.part"
    _description = "Maintenance Claim Part"

    claim_id = fields.Many2one(
        "maintenance.claim",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one("product.product", string="Part", required=True)
    quantity = fields.Float(required=True, default=1.0)
    unit_cost = fields.Float(string="Unit Cost", digits="Product Price")
    include = fields.Boolean(string="Charge", default=False)
    glass_type_id = fields.Many2one("window.tint.glass.type", string="Glass", readonly=True)
    tint_percentage_id = fields.Many2one("window.tint.percentage", string="Tint %", readonly=True)
    origin_tint_detail_id = fields.Many2one(
        "sale.order.line.tint.detail",
        string="Original Glass",
        readonly=True,
        ondelete="set null",
    )

    def write(self, vals):
        if any(part.claim_id.state != "quality" for part in self):
            raise UserError(_("You cannot change parts after the request is confirmed."))
        if not self.env.su and not self.env.user.has_group("work_orders.group_quality_officer"):
            raise UserError(_("Only quality can change the parts to charge."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and not self.env.user.has_group("work_orders.group_quality_officer"):
            if any(part.claim_id.state != "quality" for part in self):
                raise UserError(_("You cannot remove parts after the request is confirmed."))
        return super().unlink()
