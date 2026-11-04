from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from odoo.tools.misc import formatLang


class WorkOrderProduct(models.Model):
    _inherit = "car.workorder.product"

    branch_available_qty = fields.Float(
        string="Available in Branch", compute="_compute_branch_material_stock",
        digits="Product Unit of Measure",
        help="Unreserved stock in the branch warehouse and its stock sublocations, "
             "in this line's unit. Selecting a lot/serial restricts availability to that lot. "
             "Reload the order to refresh stock changed by other operations.",
    )
    availability_warehouse_id = fields.Many2one(
        "stock.warehouse", string="Material Warehouse", compute="_compute_branch_material_stock",
    )
    material_stock_shortage = fields.Boolean(compute="_compute_branch_material_stock")
    material_stock_warning = fields.Char(string="Stock Warning", compute="_compute_branch_material_stock")

    @api.depends(
        "product_id", "quantity", "used_uom_id", "lot_id", "materials_issued", "material_move_id",
        "workorder_id.branch_id", "workorder_id.company_id", "workorder_id.state",
        "workorder_id.product_ids.product_id", "workorder_id.product_ids.quantity",
        "workorder_id.product_ids.used_uom_id", "workorder_id.product_ids.lot_id",
        "workorder_id.product_ids.materials_issued", "workorder_id.product_ids.material_move_id",
    )
    @api.depends_context("company", "lang")
    def _compute_branch_material_stock(self):
        warehouses = {}
        stock = {}
        for line in self:
            line.branch_available_qty = 0
            line.availability_warehouse_id = False
            line.material_stock_shortage = False
            line.material_stock_warning = False
            product, order = line.product_id, line.workorder_id
            if not product or product.detailed_type != "product" or not order:
                continue
            company = order.company_id or self.env.company
            warehouse_key = (order.branch_id.id, company.id)
            if warehouse_key not in warehouses:
                try:
                    warehouses[warehouse_key] = (order._get_branch_warehouse(), False)
                except UserError as error:
                    # Older orders without branch configuration must remain readable.
                    warehouses[warehouse_key] = (False, str(error))
            warehouse, configuration_warning = warehouses[warehouse_key]
            if not warehouse:
                line.material_stock_warning = configuration_warning
                continue
            line.availability_warehouse_id = warehouse
            key = (warehouse.id, product.id, line.lot_id.id)
            if key not in stock:
                Quant = self.env["stock.quant"].sudo().with_company(company)
                if line.lot_id:
                    # Odoo's non-strict gather also includes untracked quants.
                    # Use the exact selected lot, as the existing Finish check does.
                    quants = Quant._gather(product, warehouse.lot_stock_id, lot_id=line.lot_id)
                    quants = quants.filtered(lambda quant: quant.lot_id == line.lot_id)
                    stock[key] = sum(quants.mapped("quantity")) - sum(quants.mapped("reserved_quantity"))
                else:
                    stock[key] = Quant._get_available_quantity(product, warehouse.lot_stock_id)
            uom = line.used_uom_id or product.uom_id
            if uom.category_id != product.uom_id.category_id:
                continue  # Existing unit validation explains this configuration error.
            available = stock[key]
            line.branch_available_qty = product.uom_id._compute_quantity(available, uom, round=False)
            if (order.state not in ("new", "confirmed", "progress") or line.materials_issued
                    or line.material_move_id or line.quantity <= 0):
                continue
            # Include the other pending parts/services that need this product.
            # An onchange pseudo-record replaces its saved origin instead of adding
            # a second copy of that line to the demand calculation.
            others = order.product_ids.filtered(lambda item:
                item != line and not (line._origin and item._origin == line._origin)
                and item.product_id == product and item.quantity > 0
                and not item.materials_issued and not item.material_move_id
                and (not line.lot_id or item.lot_id == line.lot_id)
            )
            required = uom._compute_quantity(line.quantity, product.uom_id, round=False)
            for other in others:
                other_uom = other.used_uom_id or product.uom_id
                if other_uom.category_id == product.uom_id.category_id:
                    required += other_uom._compute_quantity(other.quantity, product.uom_id, round=False)
            if float_compare(available, required, precision_rounding=product.uom_id.rounding) < 0:
                line.material_stock_shortage = True
                precision = self.env["decimal.precision"].precision_get("Product Unit of Measure")
                line.material_stock_warning = _(
                    "Insufficient stock for %(product)s in %(warehouse)s: "
                    "this order needs %(required)s %(unit)s; available %(available)s %(unit)s. "
                    "Choose an available replacement or replenish stock before issuing.",
                    product=product.display_name, warehouse=warehouse.display_name,
                    required=formatLang(self.env, product.uom_id._compute_quantity(required, uom, round=False), digits=precision),
                    available=formatLang(self.env, line.branch_available_qty, digits=precision),
                    unit=uom.display_name,
                )

    @api.onchange("product_id", "quantity", "used_uom_id", "lot_id")
    def _onchange_warn_branch_stock(self):
        # Runs after the existing product onchange has selected the unit/quantity.
        if self.material_stock_shortage:
            return {"warning": {
                "title": _("Insufficient Branch Stock"),
                "message": self.material_stock_warning,
            }}
