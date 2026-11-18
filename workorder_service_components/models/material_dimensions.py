from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_round


class MaterialBrand(models.Model):
    _name = "car.material.brand"
    _description = "Material Brand"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    _sql_constraints = [("name_unique", "unique(name)", "This brand already exists.")]


class ProductProduct(models.Model):
    _inherit = "product.product"

    material_brand_id = fields.Many2one("car.material.brand", string="Material Brand", ondelete="restrict")
    film_width_in = fields.Float(string="Film Width (in)", digits=(16, 4))
    roll_length_m = fields.Float(string="Roll Length (m)", digits=(16, 4),
        help="Physical length represented by ONE stock unit. For ROLL 15 m enter 15; for a stock unit of one metre enter 1.")
    material_total_length_in = fields.Float(string="Total Car Length Budget (in)", digits=(16, 4))
    material_total_width_in = fields.Float(string="Total Car Width Budget (in)", digits=(16, 4))
    material_tolerance_in = fields.Float(string="Part Tolerance (in)", default=5, digits=(16, 4))

    @api.constrains("film_width_in", "roll_length_m", "material_total_length_in", "material_total_width_in", "material_tolerance_in")
    def _check_material_dimensions(self):
        for product in self:
            if min(product.film_width_in, product.roll_length_m, product.material_total_length_in,
                   product.material_total_width_in, product.material_tolerance_in) < 0:
                raise ValidationError(_("Material dimensions and tolerance cannot be negative."))


class ProductTemplate(models.Model):
    _inherit = "product.template"

    material_brand_id = fields.Many2one("car.material.brand", compute="_compute_material_variant_fields", inverse="_inverse_material_brand")
    film_width_in = fields.Float(digits=(16, 4), string="Film Width (in)", compute="_compute_material_variant_fields", inverse="_inverse_film_width")
    roll_length_m = fields.Float(digits=(16, 4), string="Roll Length (m)", compute="_compute_material_variant_fields", inverse="_inverse_roll_length")
    material_total_length_in = fields.Float(digits=(16, 4), string="Total Car Length Budget (in)", compute="_compute_material_variant_fields", inverse="_inverse_material_length")
    material_total_width_in = fields.Float(digits=(16, 4), string="Total Car Width Budget (in)", compute="_compute_material_variant_fields", inverse="_inverse_material_width")
    material_tolerance_in = fields.Float(digits=(16, 4), string="Part Tolerance (in)", compute="_compute_material_variant_fields", inverse="_inverse_material_tolerance")

    @api.depends("product_variant_ids.material_brand_id", "product_variant_ids.film_width_in", "product_variant_ids.roll_length_m",
                 "product_variant_ids.material_total_length_in", "product_variant_ids.material_total_width_in", "product_variant_ids.material_tolerance_in")
    def _compute_material_variant_fields(self):
        for name in ("material_brand_id", "film_width_in", "roll_length_m", "material_total_length_in", "material_total_width_in", "material_tolerance_in"):
            self._compute_template_field_from_variant_field(name)

    def _inverse_material_brand(self):
        self._set_product_variant_field("material_brand_id")

    def _inverse_film_width(self):
        self._set_product_variant_field("film_width_in")

    def _inverse_roll_length(self):
        self._set_product_variant_field("roll_length_m")

    def _inverse_material_length(self):
        self._set_product_variant_field("material_total_length_in")

    def _inverse_material_width(self):
        self._set_product_variant_field("material_total_width_in")

    def _inverse_material_tolerance(self):
        self._set_product_variant_field("material_tolerance_in")

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        for template, values in zip(templates, vals_list):
            if len(template.product_variant_ids) == 1:
                metadata = {name: values[name] for name in ("material_brand_id", "film_width_in", "roll_length_m",
                    "material_total_length_in", "material_total_width_in", "material_tolerance_in") if name in values}
                if metadata:
                    template.product_variant_id.write(metadata)
        return templates


class MaterialRecipe(models.AbstractModel):
    _name = "car.material.recipe"
    _description = "Material Measurement Configuration"

    usage_mode = fields.Selection([("quantity", "Quantity"), ("roll", "Film Dimensions")], required=True, default="quantity")
    standard_length_in = fields.Float(string="Standard Length (in)", digits=(16, 4))
    standard_width_in = fields.Float(string="Standard Width (in)", digits=(16, 4))
    allowed_brand_ids = fields.Many2many("car.material.brand", string="Allowed Brands")

    @api.constrains("usage_mode", "standard_length_in", "standard_width_in", "product_id", "allowed_brand_ids")
    def _check_recipe_dimensions(self):
        for line in self:
            if line.standard_length_in < 0 or line.standard_width_in < 0:
                raise ValidationError(_("Dimensions cannot be negative."))
            if line.usage_mode == "roll" and (line.standard_length_in <= 0 or line.standard_width_in <= 0):
                raise ValidationError(_("Enter positive standard length and width for film materials."))
            if line.product_id and line.allowed_brand_ids and line.product_id.material_brand_id not in line.allowed_brand_ids:
                raise ValidationError(_("The material must belong to an allowed brand."))


class CarBom(models.Model):
    _name = "car.bom"
    _inherit = ["car.bom", "car.material.recipe"]

    quantity = fields.Float(digits=(16, 4))

    @api.constrains("product_id", "material_category_id", "service_part_id", "usage_mode", "product_uom_id", "quantity")
    def _check_category_recipe(self):
        for line in self:
            if not line.product_id and not (line.service_part_id and line.material_category_id):
                raise ValidationError(_("Select a product or a material category on a configured service."))
            if line.usage_mode == "quantity" and (line.quantity <= 0 or not line.product_uom_id):
                raise ValidationError(_("Enter a positive quantity and a unit of measure."))


class BatchLine(models.TransientModel):
    _name = "car.service.component.batch.line"
    _inherit = ["car.service.component.batch.line", "car.material.recipe"]


_SNAPSHOT_FIELDS = {"usage_mode", "standard_length_in", "standard_width_in", "allowed_brand_ids"}
_ACTUAL_FIELDS = {"actual_length_in", "actual_width_in", "material_brand_id"}


class WorkOrderProduct(models.Model):
    _inherit = "car.workorder.product"

    quantity = fields.Float(digits=(16, 4))
    suggested_qty = fields.Float(digits=(16, 4))

    usage_mode = fields.Selection([("quantity", "Quantity"), ("roll", "Film Dimensions")], default="quantity", required=True)
    standard_length_in = fields.Float(string="Standard Length (in)", digits=(16, 4))
    standard_width_in = fields.Float(string="Standard Width (in)", digits=(16, 4))
    actual_length_in = fields.Float(string="Actual Length (in)", digits=(16, 4))
    actual_width_in = fields.Float(string="Actual Width (in)", digits=(16, 4))
    film_width_in = fields.Float(string="Film Width (in)", readonly=True, digits=(16, 4))
    roll_length_m = fields.Float(string="Roll Length (m)", readonly=True, digits=(16, 4))
    allowed_brand_ids = fields.Many2many("car.material.brand", string="Allowed Brands")
    material_brand_id = fields.Many2one("car.material.brand", string="Brand", ondelete="restrict")
    dimension_warning = fields.Char(string="Measurement Warning", compute="_compute_dimension_warning")

    @api.model
    def _values_from_component(self, service, component):
        vals = super()._values_from_component(service, component)
        vals.update(usage_mode=component.usage_mode,
            standard_length_in=component.standard_length_in, standard_width_in=component.standard_width_in,
            actual_length_in=component.standard_length_in, actual_width_in=component.standard_width_in,
            allowed_brand_ids=[fields.Command.set(component.allowed_brand_ids.ids)],
            material_brand_id=component.product_id.material_brand_id.id)
        return vals

    @api.model
    def _apply_material_precision(self):
        """Only precision metadata changes; balances and posted moves stay intact."""
        precision = self.env["decimal.precision"].search([("name", "=", "Product Unit of Measure")], limit=1)
        if precision and precision.digits < 4:
            precision.digits = 4
        recipes = self.env["car.bom"].with_context(active_test=False).search([("service_part_id", "!=", False)])
        film = self.env["product.product"].with_context(active_test=False).search([("film_width_in", ">", 0), ("roll_length_m", ">", 0)])
        units = recipes.product_uom_id | recipes.product_id.uom_id | film.uom_id
        units.filtered(lambda u: .0001 < u.rounding < 1).write({"rounding": .0001})

    def _film_quantity(self, length, width):
        self.ensure_one()
        if not self.product_id:
            return 0
        if self.film_width_in <= 0 or self.roll_length_m <= 0:
            raise ValidationError(_("Define film width and the roll length represented by one stock unit on the raw material."))
        if self.product_id.uom_id.rounding >= 1:
            raise ValidationError(_("Film stock needs a unit that permits fractions of a roll (rounding below 1)."))
        if self.product_id.uom_id.rounding > .0001:
            raise ValidationError(_("Film stock needs four-decimal unit precision. Set the stock unit rounding to 0.0001 or smaller."))
        # Both cut dimensions contribute to area. Convert inÂ² to mÂ², then to
        # fractions of the selected stock unit; Odoo handles compatible UoMs.
        base_qty = length * width * 0.0254 / (self.film_width_in * self.roll_length_m)
        uom = self.used_uom_id or self.product_id.uom_id
        quantity = self.product_id.uom_id._compute_quantity(base_qty, uom, round=False)
        precision = 4
        return float_round(quantity, precision_rounding=max(uom.rounding, 10 ** -precision), rounding_method="UP")

    def _dimension_values(self):
        self.ensure_one()
        return {"quantity": self._film_quantity(self.actual_length_in, self.actual_width_in),
                "suggested_qty": self._film_quantity(self.standard_length_in, self.standard_width_in)}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            component = self.env["car.bom"].browse(vals.get("source_component_id"))
            if component:
                defaults = self._values_from_component(component.service_id, component)
                for key in _SNAPSHOT_FIELDS | {"actual_length_in", "actual_width_in", "material_brand_id"}:
                    vals.setdefault(key, defaults[key])
            if vals.get("usage_mode") == "roll":
                product = self.env["product.product"].browse(vals.get("product_id"))
                vals.update(film_width_in=product.film_width_in, roll_length_m=product.roll_length_m)
                temporary = self.new(vals)
                vals.update(temporary._dimension_values())
        return super().create(vals_list)

    def write(self, vals):
        fields_changed = set(vals)
        if fields_changed & _ACTUAL_FIELDS:
            for order in self.workorder_id.sorted("id"):
                self.env.cr.execute("SELECT id FROM car_work_order WHERE id = %s FOR UPDATE", (order.id,))
            self.source_task_id.invalidate_recordset(["materials_issued"])
        for line in self:
            if fields_changed & (_SNAPSHOT_FIELDS | _ACTUAL_FIELDS | {"film_width_in", "roll_length_m"}):
                if line.materials_issued or line.material_move_id.state == "done":
                    raise UserError(_("Issued material measurements cannot be changed."))
                if fields_changed & (_SNAPSHOT_FIELDS | {"film_width_in", "roll_length_m"}):
                    raise UserError(_("Configured measurements and allowed brands are saved with the order and cannot be changed."))
                if line.workorder_id.state not in ("new", "confirmed", "progress"):
                    raise UserError(_("Measurements can only be entered on open work orders."))
            if line.usage_mode == "roll" and fields_changed & {"quantity", "suggested_qty"} and not fields_changed & {"product_id", "actual_length_in", "actual_width_in", "used_uom_id"}:
                raise UserError(_("Enter actual length and width; film quantity is calculated automatically."))
        result = True
        for line in self:
            values = dict(vals)
            if values.get("source_component_id") and not line.source_component_id and line.workorder_id.state == "new":
                component = self.env["car.bom"].browse(values["source_component_id"])
                defaults = self._values_from_component(component.service_id, component)
                for name in _SNAPSHOT_FIELDS | {"actual_length_in", "actual_width_in", "material_brand_id"}:
                    values[name] = defaults[name]
                if component.usage_mode == "roll":
                    temporary = self.new(dict(defaults, product_id=line.product_id.id,
                        used_uom_id=(line.used_uom_id or component.product_uom_id or line.product_id.uom_id).id,
                        film_width_in=line.product_id.film_width_in, roll_length_m=line.product_id.roll_length_m))
                    values.update(film_width_in=temporary.film_width_in, roll_length_m=temporary.roll_length_m)
                    values.update(temporary._dimension_values())
            if ("product_id" in values and line.usage_mode == "quantity" and line.source_component_id
                    and not line.source_component_id.product_id and line.used_uom_id):
                product = self.env["product.product"].browse(values["product_id"])
                if product and product.uom_id.category_id != line.used_uom_id.category_id:
                    raise ValidationError(_("Choose a material compatible with the configured quantity unit."))
                values.setdefault("used_uom_id", line.used_uom_id.id)
            if line.usage_mode == "roll" and fields_changed & {"product_id", "actual_length_in", "actual_width_in", "used_uom_id"}:
                temporary = self.new({name: line[name].id if line._fields[name].type == "many2one" else line[name]
                    for name in ("product_id", "used_uom_id", "film_width_in", "roll_length_m", "actual_length_in", "actual_width_in", "standard_length_in", "standard_width_in")})
                if "product_id" in values:
                    product = self.env["product.product"].browse(values["product_id"])
                    values.update(film_width_in=product.film_width_in, roll_length_m=product.roll_length_m)
                    values.setdefault("used_uom_id", product.uom_id.id)
                temporary.update(values)
                values.update(temporary._dimension_values())
            if (line.source_task_id and line.workorder_id.state in ("confirmed", "progress")
                    and fields_changed <= (_ACTUAL_FIELDS | {"product_id", "lot_id", "quantity", "used_uom_id", "tag_id"})
                    and (fields_changed <= _ACTUAL_FIELDS or (line.usage_mode == "roll" and
                         ("product_id" not in vals or line.material_category_id)) or
                         (line.material_category_id and "product_id" in vals))):
                # Keep existing issued-line checks and order locks in the parent.
                result = super(WorkOrderProduct, line.with_context(contract_upsell_sync=True)).write(values) and result
            else:
                result = super(WorkOrderProduct, line).write(values) and result
        return result

    @api.constrains("product_id", "allowed_brand_ids", "material_brand_id", "actual_length_in", "actual_width_in", "usage_mode", "source_task_id", "source_component_id", "material_category_id")
    def _check_actual_dimensions(self):
        for line in self:
            if min(line.actual_length_in, line.actual_width_in) < 0:
                raise ValidationError(_("Actual dimensions cannot be negative."))
            if line.material_category_id and line.product_id and not line.material_brand_id:
                fixed = line.source_component_id.product_id == line.product_id
                if not line.source_component_id and line.service_id:
                    fixed = bool(self.env["car.bom"].search_count([
                        ("service_id", "=", line.service_id.id), ("product_id", "=", line.product_id.id),
                        ("service_part_id", "!=", False)]))
                if not fixed:
                    raise ValidationError(_("Choose the material brand before selecting a product."))
            if line.usage_mode == "roll":
                tolerance = line.source_task_id.material_tolerance_in if line.source_task_id else 5
                for label, actual, standard in ((_("length"), line.actual_length_in, line.standard_length_in),
                                                 (_("width"), line.actual_width_in, line.standard_width_in)):
                    limit = standard + tolerance
                    if float_compare(actual, limit, precision_digits=4) > 0:
                        raise ValidationError(_(
                            "The actual %(dimension)s for %(part)s cannot exceed %(limit).4f inches (standard plus part tolerance).",
                            dimension=label, part=line.part_id.display_name or _("this material"), limit=limit))
            if line.material_brand_id and line.allowed_brand_ids and line.material_brand_id not in line.allowed_brand_ids:
                raise ValidationError(_("Choose one of the allowed brands."))
            if line.product_id:
                if line.allowed_brand_ids and line.product_id.material_brand_id not in line.allowed_brand_ids:
                    raise ValidationError(_("The product must belong to an allowed brand."))
                if line.material_brand_id and line.product_id.material_brand_id != line.material_brand_id:
                    raise ValidationError(_("The selected product belongs to another brand."))
            if line.usage_mode == "roll" and line.product_id and line.actual_width_in > line.film_width_in:
                raise ValidationError(_("The cut width cannot exceed the selected film width."))

    @api.onchange("material_brand_id")
    def _onchange_material_brand(self):
        if self.product_id and self.material_brand_id and self.product_id.material_brand_id != self.material_brand_id:
            self.product_id = False
            self.lot_id = False

    @api.onchange("product_id")
    def _onchange_film_product(self):
        if self.usage_mode == "roll":
            self.film_width_in = self.product_id.film_width_in
            self.roll_length_m = self.product_id.roll_length_m
            self._onchange_film_dimensions()
        elif self.source_component_id and not self.source_component_id.product_id:
            self.used_uom_id = self.source_component_id.product_uom_id

    @api.onchange("actual_length_in", "actual_width_in", "used_uom_id")
    def _onchange_film_dimensions(self):
        if self.usage_mode == "roll":
            if not self.product_id or (self.film_width_in > 0 and self.roll_length_m > 0):
                self.update(self._dimension_values())
        if self.dimension_warning:
            return {"warning": {"title": _("Material Measurement Warning"), "message": self.dimension_warning}}

    @api.depends("actual_length_in", "actual_width_in", "standard_length_in", "standard_width_in", "usage_mode",
                 "source_task_id.material_tolerance_in", "source_task_id.material_budget_warning")
    def _compute_dimension_warning(self):
        for line in self:
            messages = []
            if line.usage_mode == "roll":
                tolerance = line.source_task_id.material_tolerance_in if line.source_task_id else 5
                if line.actual_length_in > line.standard_length_in + tolerance + 1e-6:
                    messages.append(_("Actual length exceeds the standard plus %(tolerance)s inches.", tolerance=tolerance))
                if line.actual_width_in > line.standard_width_in + tolerance + 1e-6:
                    messages.append(_("Actual width exceeds the standard plus %(tolerance)s inches.", tolerance=tolerance))
                if line.source_task_id.material_budget_warning:
                    messages.append(line.source_task_id.material_budget_warning)
            line.dimension_warning = " ".join(messages) or False


class WorkOrderService(models.Model):
    _inherit = "car.workorder.service"

    material_total_length_in = fields.Float(digits=(16, 4), string="Car Length Budget (in)", readonly=True)
    material_total_width_in = fields.Float(digits=(16, 4), string="Car Width Budget (in)", readonly=True)
    material_tolerance_in = fields.Float(digits=(16, 4), string="Part Tolerance (in)", readonly=True, default=5)
    material_used_length_in = fields.Float(digits=(16, 4), string="Total Used Length (in)", compute="_compute_material_totals")
    material_used_width_in = fields.Float(digits=(16, 4), string="Total Used Width (in)", compute="_compute_material_totals")
    material_used_area_m2 = fields.Float(digits=(16, 4), string="Total Film Area (mÂ²)", compute="_compute_material_totals")
    material_budget_warning = fields.Char(string="Car Budget Warning", compute="_compute_material_totals")

    def _get_service_boms(self):
        self.ensure_one()
        return super()._get_service_boms() | self.workorder_id.product_ids.filtered(
            lambda row: row.source_task_id == self).source_component_id

    def _ensure_qa_items(self):
        result = super()._ensure_qa_items()
        for task in self:
            for line in task.workorder_id.product_ids.filtered(lambda row: row.source_task_id == task and row.source_component_id):
                items = task.qa_check_item_ids.filtered(lambda item: item.bom_id == line.source_component_id)
                # Once created, keep completed checklist history unchanged.
                for item in items.filtered(lambda row: not row.checked):
                    item.sudo().write({"product_id": line.product_id.id, "name": line.product_id.display_name or line.material_category_id.display_name,
                        "quantity": line.quantity, "unit_cost": line.product_id.standard_price})
        return result

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            product = self.env["product.product"].browse(vals.get("product_id"))
            for name in ("material_total_length_in", "material_total_width_in", "material_tolerance_in"):
                vals[name] = product[name] if product else (5 if name == "material_tolerance_in" else 0)
        return super().create(vals_list)

    def write(self, vals):
        if {"material_total_length_in", "material_total_width_in", "material_tolerance_in"} & set(vals):
            raise UserError(_("The car material budget is a saved service configuration."))
        result = super().write(vals)
        if "product_id" in vals:
            for task in self.filtered(lambda row: row.workorder_id.state == "new"):
                super(WorkOrderService, task).write({name: task.product_id[name] for name in
                    ("material_total_length_in", "material_total_width_in", "material_tolerance_in")})
        return result

    @api.depends("workorder_id.product_ids.actual_length_in", "workorder_id.product_ids.actual_width_in",
                 "workorder_id.product_ids.usage_mode", "workorder_id.product_ids.source_task_id",
                 "material_total_length_in", "material_total_width_in")
    def _compute_material_totals(self):
        for task in self:
            lines = task.workorder_id.product_ids.filtered(lambda row: row.source_task_id == task and row.usage_mode == "roll")
            task.material_used_length_in = sum(lines.mapped("actual_length_in"))
            task.material_used_width_in = sum(lines.mapped("actual_width_in"))
            task.material_used_area_m2 = sum(row.actual_length_in * row.actual_width_in * 0.0254 ** 2 for row in lines)
            over = ((task.material_total_length_in and task.material_used_length_in > task.material_total_length_in + 1e-6)
                    or (task.material_total_width_in and task.material_used_width_in > task.material_total_width_in + 1e-6))
            task.material_budget_warning = _("Total film measurements exceed this service's car budget.") if over else False


class WorkOrder(models.Model):
    _inherit = "car.work.order"

    material_used_length_m = fields.Float(digits=(16, 4), string="Total Car Film Length (m)", compute="_compute_car_film_totals")
    material_used_width_m = fields.Float(digits=(16, 4), string="Total Car Film Width (m)", compute="_compute_car_film_totals")
    material_used_area_m2 = fields.Float(digits=(16, 4), string="Total Car Film Area (mÂ²)", compute="_compute_car_film_totals")

    @api.depends("service_ids.material_used_length_in", "service_ids.material_used_width_in", "service_ids.material_used_area_m2")
    def _compute_car_film_totals(self):
        for order in self:
            order.material_used_length_m = sum(order.service_ids.mapped("material_used_length_in")) * 0.0254
            order.material_used_width_m = sum(order.service_ids.mapped("material_used_width_in")) * 0.0254
            order.material_used_area_m2 = sum(order.service_ids.mapped("material_used_area_m2"))
