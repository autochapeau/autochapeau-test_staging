from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class WorkorderServiceQaFault(models.Model):
    _name = "workorder.service.qa.fault"
    _description = "Workorder Task QA Fault"
    _order = "refuse_date desc, id desc"

    name = fields.Char(string="Reference", compute="_compute_name", store=True)
    refuse_date = fields.Datetime(
        string="Refuse Date",
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    fault_type = fields.Selection(
        [
            ("technician", "Technician Fault"),
            ("supplier", "Supplier / Product Fault"),
        ],
        string="Fault Type",
        required=True,
        index=True,
    )
    reason = fields.Text(string="Reason", required=True)

    service_id = fields.Many2one(
        "car.workorder.service",
        string="Task",
        required=True,
        ondelete="cascade",
        index=True,
    )
    workorder_id = fields.Many2one(
        "car.work.order",
        string="Work Order",
        related="service_id.workorder_id",
        store=True,
        index=True,
    )
    service_product_id = fields.Many2one(
        "product.product",
        string="Service",
        related="service_id.product_id",
        store=True,
    )
    branch_id = fields.Many2one(
        "hr.department",
        string="Branch",
        related="service_id.branch_id",
        store=False,
    )
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        related="workorder_id.vehicle_id",
        store=True,
    )

    qa_check_item_id = fields.Many2one(
        "workorder.service.qa.check.item",
        string="QA Check Item",
        ondelete="set null",
    )
    bom_id = fields.Many2one(
        "car.bom",
        string="BOM Line",
        ondelete="set null",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Faulty Part",
        required=True,
        ondelete="restrict",
        index=True,
        help="BOM component where the fault was found.",
    )
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    unit_cost = fields.Float(string="Unit Cost", digits="Product Price")
    cost = fields.Float(
        string="BOM Cost",
        digits="Product Price",
        compute="_compute_cost",
        store=True,
        help="Reference cost of the faulty BOM part (qty × unit cost).",
    )
    technician_cost = fields.Float(
        string="Charged to Technician",
        digits="Product Price",
        help="Amount charged to the technician. Editable when the company "
             "decides to share the cost.",
    )
    company_cost = fields.Float(
        string="Charged to Company",
        digits="Product Price",
        help="Amount borne by the company. Editable when the company "
             "decides to share the cost.",
    )

    employee_id = fields.Many2one(
        "hr.employee",
        string="Technician",
        index=True,
        help="Responsible technician when fault type is Technician.",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Supplier",
        index=True,
        help="Supplier when fault type is Supplier / Product.",
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Delivery",
        readonly=True,
        copy=False,
        index=True,
        help="Outgoing delivery created to replace the faulty BOM part from stock.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            bom_cost = (vals.get("quantity") or 0.0) * (vals.get("unit_cost") or 0.0)
            if "technician_cost" not in vals and "company_cost" not in vals:
                if vals.get("fault_type") == "technician":
                    vals["technician_cost"] = bom_cost
                    vals["company_cost"] = 0.0
                else:
                    vals["technician_cost"] = 0.0
                    vals["company_cost"] = bom_cost
            elif "technician_cost" not in vals:
                vals["technician_cost"] = max(
                    bom_cost - (vals.get("company_cost") or 0.0), 0.0
                )
            elif "company_cost" not in vals:
                vals["company_cost"] = max(
                    bom_cost - (vals.get("technician_cost") or 0.0), 0.0
                )
        return super().create(vals_list)

    def _get_qa_delivery_warehouse(self):
        """Warehouse of the work order branch (Branch A → warehouse of Branch A)."""
        self.ensure_one()
        company = self.company_id or self.env.company
        workorder = self.workorder_id
        if not workorder:
            raise UserError(_("QA fault has no work order; cannot create a delivery."))
        branch = workorder.branch_id
        if not branch:
            raise UserError(
                _("Work order %s has no branch. Set the branch before creating a "
                  "replacement delivery.")
                % workorder.display_name
            )
        Warehouse = self.env["stock.warehouse"]
        if "branch_id" not in Warehouse._fields:
            raise UserError(
                _("Warehouse branch linking is not available. "
                  "Install/upgrade work_orders warehouse branch support.")
            )
        warehouse = Warehouse.search(
            [
                ("branch_id", "=", branch.id),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        if not warehouse:
            raise UserError(
                _("No warehouse is linked to branch '%s'. "
                  "Open Inventory → Configuration → Warehouses and set the Branch "
                  "on the correct warehouse.")
                % branch.display_name
            )
        return warehouse

    def _get_qa_customer_location(self, company):
        """Partner Locations / Customers for outgoing deliveries."""
        location = self.env.ref("stock.stock_location_customers", raise_if_not_found=False)
        if location and (not location.company_id or location.company_id == company):
            return location
        location = self.env["stock.location"].search(
            [
                ("usage", "=", "customer"),
                "|",
                ("company_id", "=", False),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        if not location:
            raise UserError(
                _("No customer location found. Check Inventory → Configuration → Locations.")
            )
        return location

    def _create_replacement_delivery(self):
        """Create draft outgoing delivery from the WO branch warehouse stock → Customers."""
        faults = self.filtered(lambda f: f.product_id and not f.picking_id)
        if not faults:
            return self.env["stock.picking"]

        warehouse = faults[0]._get_qa_delivery_warehouse()
        company = faults[0].company_id or self.env.company
        picking_type = warehouse.out_type_id
        if not picking_type:
            raise UserError(
                _("Warehouse '%s' has no Delivery Orders operation type.")
                % warehouse.display_name
            )

        # Source = stock of the branch warehouse (same warehouse the WO works on)
        location_src = warehouse.lot_stock_id
        if not location_src:
            location_src = picking_type.default_location_src_id
        if not location_src:
            raise UserError(
                _("Warehouse '%s' has no stock location to take products from.")
                % warehouse.display_name
            )

        # Destination = Customers (outgoing delivery)
        location_dest = picking_type.default_location_dest_id
        if not location_dest or location_dest.usage != "customer":
            location_dest = faults[0]._get_qa_customer_location(company)

        workorder = faults[0].workorder_id
        partner = workorder.partner_id if workorder else False
        origin = (
            _("QA Rework - %s") % workorder.name
            if workorder
            else _("QA Rework")
        )

        move_commands = []
        for fault in faults:
            product = fault.product_id
            move_commands.append(
                Command.create(
                    {
                        "name": product.display_name,
                        "product_id": product.id,
                        "product_uom_qty": fault.quantity or 1.0,
                        "product_uom": product.uom_id.id,
                        "location_id": location_src.id,
                        "location_dest_id": location_dest.id,
                    }
                )
            )

        picking_vals = {
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "origin": origin,
            "partner_id": partner.id if partner else False,
            "move_ids": move_commands,
            "company_id": company.id,
        }
        if "branch_id" in self.env["stock.picking"]._fields and workorder.branch_id:
            picking_vals["branch_id"] = workorder.branch_id.id

        picking = self.env["stock.picking"].sudo().create(picking_vals)
        faults.write({"picking_id": picking.id})
        return picking

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("No delivery linked to this QA fault."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Delivery"),
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_id.id,
            "target": "current",
        }

    @api.onchange("technician_cost")
    def _onchange_technician_cost(self):
        self.company_cost = (self.cost or 0.0) - (self.technician_cost or 0.0)

    @api.onchange("company_cost")
    def _onchange_company_cost(self):
        self.technician_cost = (self.cost or 0.0) - (self.company_cost or 0.0)

    @api.depends("product_id", "fault_type", "service_id")
    def _compute_name(self):
        for fault in self:
            part = fault.product_id.display_name if fault.product_id else _("Part")
            fault_label = dict(fault._fields["fault_type"].selection).get(
                fault.fault_type, ""
            )
            service = fault.service_product_id.display_name if fault.service_product_id else ""
            fault.name = f"{fault_label}: {part}" + (f" ({service})" if service else "")

    @api.depends("quantity", "unit_cost")
    def _compute_cost(self):
        for fault in self:
            fault.cost = (fault.quantity or 0.0) * (fault.unit_cost or 0.0)
