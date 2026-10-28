from odoo import _, api, fields, models
from odoo.exceptions import UserError


_COMPONENT_LOCKED_FIELDS = frozenset({"suggested_qty", "used_uom_id"})


def _is_upsell_sync(env):
    return bool(
        env.context.get("contract_upsell_sync")
        or env.context.get("extern_upsell_sync")
    )


class CarWorkOrderProduct(models.Model):
    _inherit = "car.workorder.product"

    service_id = fields.Many2one(
        "product.product",
        string="Service",
        domain="[('detailed_type', '=', 'service')]",
    )
    suggested_qty = fields.Float(string="Suggested Quantity")
    product_uom_category_id = fields.Many2one(
        related="product_id.uom_id.category_id",
    )
    used_uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        domain="[('category_id', '=', product_uom_category_id)]",
    )

    @api.onchange("service_id")
    def _onchange_service_id_load_components(self):
        """Selecting a service loads its components. Selecting a tag only filters."""
        order = self.workorder_id
        if order and order.state != "new":
            return
        service = self.service_id
        if not service:
            return
        # Component lines are created with their product already set.
        if self.product_id and service.bom_ids.filtered(lambda bom: bom.product_id == self.product_id):
            return
        self.product_id = False
        self.suggested_qty = 0.0
        self.quantity = 0.0
        self.used_uom_id = False
        self.tag_id = False
        components = service.bom_ids.filtered("product_id")
        if not components:
            self.tag_id = service.service_tag_id
            return
        already = set()
        if order:
            already = {
                (line.service_id.id, line.product_id.id)
                for line in order.product_ids
                if line != self and line.service_id and line.product_id
            }
        pending = [
            component
            for component in components
            if (service.id, component.product_id.id) not in already
        ]
        if not pending:
            self.tag_id = service.service_tag_id
            return
        first, *rest = pending
        self._apply_component(service, first)
        if rest and order:
            order.product_ids = [
                fields.Command.create(self._values_from_component(service, component))
                for component in rest
            ]

    @api.onchange("tag_id")
    def _onchange_tag_id(self):
        if self.tag_id and self.product_id and self.tag_id not in self.product_id.product_tag_ids:
            self.product_id = False

    @api.onchange("product_id")
    def _onchange_product_id_component_qty(self):
        if not self.product_id:
            self.suggested_qty = 0.0
            self.used_uom_id = False
            return
        component = self.env["car.bom"]
        if self.service_id:
            component = self.service_id.bom_ids.filtered(
                lambda bom: bom.product_id == self.product_id
            )[:1]
        if component:
            self.suggested_qty = component.quantity
            self.quantity = component.quantity
            self.used_uom_id = component.product_uom_id or self.product_id.uom_id
        else:
            self.suggested_qty = 0.0
            self.used_uom_id = self.product_id.uom_id

    @api.model
    def _values_from_component(self, service, component):
        product = component.product_id
        tag = service.service_tag_id
        uom = component.product_uom_id or product.uom_id
        return {
            "service_id": service.id,
            "tag_id": tag.id if tag and product and tag in product.product_tag_ids else False,
            "product_id": product.id,
            "suggested_qty": component.quantity,
            "quantity": component.quantity,
            "used_uom_id": uom.id if uom else False,
        }

    def _apply_component(self, service, component):
        self.ensure_one()
        values = self._values_from_component(service, component)
        product = component.product_id
        self.suggested_qty = values["suggested_qty"]
        self.quantity = values["quantity"]
        self.used_uom_id = values["used_uom_id"] or False
        if values["tag_id"]:
            self.tag_id = values["tag_id"]
        elif self.tag_id and self.tag_id not in product.product_tag_ids:
            self.tag_id = False
        self.product_id = product

    @api.model_create_multi
    def create(self, vals_list):
        self._complete_component_vals(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        if not _is_upsell_sync(self.env) and _COMPONENT_LOCKED_FIELDS & set(vals):
            locked_lines = self.filtered(lambda line: line.workorder_id.state != "new")
            if locked_lines:
                raise UserError(_(
                    "You cannot modify products after the work order has been confirmed."
                ))
        return super().write(vals)

    @api.model
    def _complete_component_vals(self, vals_list):
        Product = self.env["product.product"]
        Bom = self.env["car.bom"]
        for vals in vals_list:
            service = Product.browse(vals["service_id"]) if vals.get("service_id") else Product
            product = Product.browse(vals["product_id"]) if vals.get("product_id") else Product
            component = Bom.browse()
            if service and product:
                component = Bom.search([
                    ("service_id", "=", service.id),
                    ("product_id", "=", product.id),
                ], limit=1)
            if component and "suggested_qty" not in vals:
                vals["suggested_qty"] = component.quantity
            if "used_uom_id" not in vals:
                uom = component.product_uom_id if component else product.uom_id
                if uom:
                    vals["used_uom_id"] = uom.id
            if (
                "tag_id" not in vals
                and service.service_tag_id
                and product
                and service.service_tag_id in product.product_tag_ids
            ):
                vals["tag_id"] = service.service_tag_id.id

    def _auto_init(self):
        result = super()._auto_init()
        self.env.cr.execute(
            """
            UPDATE car_workorder_product AS line
               SET used_uom_id = COALESCE(
                    (
                        SELECT bom.product_uom_id
                          FROM car_bom AS bom
                         WHERE bom.service_id = line.service_id
                           AND bom.product_id = line.product_id
                           AND bom.product_uom_id IS NOT NULL
                         LIMIT 1
                    ),
                    template.uom_id
               )
              FROM product_product AS product
              JOIN product_template AS template
                ON template.id = product.product_tmpl_id
             WHERE line.product_id = product.id
               AND line.used_uom_id IS NULL
            """
        )
        return result
