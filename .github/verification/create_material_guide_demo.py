"""Create named, fictional guide examples on TEST only. Idempotent XML IDs."""
import json
from odoo import Command
assert env.cr.dbname == "autochapeau_prod_test", "Guide examples are TEST-only"
qa = env(context=dict(env.context, tracking_disable=True, mail_create_nosubscribe=True, mail_notrack=True, no_reset_password=True))

def ensure(key, model, values):
    xmlid = "workorder_service_components.guide_demo_" + key
    record = qa.ref(xmlid, raise_if_not_found=False)
    if record and record.exists():
        assert record._name == model
        return record
    record = qa[model].create(values)
    data = qa["ir.model.data"].search([("module", "=", "workorder_service_components"), ("name", "=", "guide_demo_" + key)])
    if data:
        data.write({"model": model, "res_id": record.id})
    else:
        qa["ir.model.data"].create({"module": "workorder_service_components", "name": "guide_demo_" + key, "model": model, "res_id": record.id, "noupdate": True})
    return record

films = ensure("films", "product.category", {"name": "DEMO Guide | Films", "is_main_material_category": True})
liquids = ensure("liquids", "product.category", {"name": "DEMO Guide | Liquids", "is_main_material_category": True})
marvel = ensure("marvel", "car.material.brand", {"name": "DEMO Marvel"})
miracle = ensure("miracle", "car.material.brand", {"name": "DEMO Miracle"})
unit = qa.ref("uom.product_uom_unit")
roll = ensure("roll", "uom.uom", {"name": "DEMO Roll", "category_id": unit.category_id.id, "uom_type": "smaller", "factor": 1, "rounding": .000001})
litre = qa.ref("uom.product_uom_litre")
ml = ensure("ml", "uom.uom", {"name": "DEMO ml", "category_id": litre.category_id.id, "uom_type": "smaller", "factor": 1000, "rounding": .001})
film_a = ensure("film_a", "product.product", {"name": "DEMO Marvel Film 60 in / 15 m", "detailed_type": "product", "categ_id": films.id, "uom_id": roll.id, "uom_po_id": roll.id, "material_brand_id": marvel.id, "film_width_in": 60, "roll_length_m": 15, "default_code": "GUIDE-F60"})
film_b = ensure("film_b", "product.product", {"name": "DEMO Miracle Film 70 in / 30 m", "detailed_type": "product", "categ_id": films.id, "uom_id": roll.id, "uom_po_id": roll.id, "material_brand_id": miracle.id, "film_width_in": 70, "roll_length_m": 30, "default_code": "GUIDE-F70"})
liquid = ensure("liquid", "product.product", {"name": "DEMO Cleaning Liquid", "detailed_type": "product", "categ_id": liquids.id, "uom_id": litre.id, "uom_po_id": litre.id, "default_code": "GUIDE-LIQ"})
right = ensure("right", "car.part", {"name": "DEMO Right Window"})
left = ensure("left", "car.part", {"name": "DEMO Left Window"})
attribute = ensure("size", "product.attribute", {"name": "DEMO Car Size"})
values = [ensure("size_"+label.lower(), "product.attribute.value", {"name": label, "attribute_id": attribute.id}) for label in ("Small", "Medium", "Large", "XL")]
template = ensure("service", "product.template", {"name": "DEMO Guide | Window Tinting", "detailed_type": "service", "attribute_line_ids": [Command.create({"attribute_id": attribute.id, "value_ids": [Command.set([v.id for v in values])]})]})
variants = {}
measurements = {"Small": (15,20), "Medium": (18,22), "Large": (21,24), "XL": (24,26)}
for product in template.product_variant_ids:
    label = product.product_template_attribute_value_ids.product_attribute_value_id.name
    variants[label] = product
    length,width = measurements[label]
    product.write({"material_total_length_in": length*2, "material_total_width_in": width*2, "material_tolerance_in": 5})
batch = ensure("batch", "car.service.component.batch", {"product_tmpl_id": template.id, "part_ids": [Command.set((right|left).ids)], "service_ids": [Command.set(template.product_variant_ids.ids)], "line_ids": [Command.create({"material_category_id": films.id, "usage_mode": "roll", "standard_length_in": 15, "standard_width_in": 20, "quantity": 1, "allowed_brand_ids": [Command.set((marvel|miracle).ids)]})], "variant_line_ids": [Command.create({"service_id": variants[label].id, "standard_length_in": length, "standard_width_in": width, "quantity": 1}) for label,(length,width) in measurements.items()]})
batch.action_apply()
paint = ensure("paint", "product.product", {"name": "DEMO Guide | Whole-Service Liquid", "detailed_type": "service"})
liquid_batch = ensure("liquid_batch", "car.service.component.batch", {"product_tmpl_id": paint.product_tmpl_id.id, "service_ids": [Command.set(paint.ids)], "line_ids": [Command.create({"material_category_id": liquids.id, "quantity": 250, "product_uom_id": ml.id, "usage_mode": "quantity"})]})
liquid_batch.action_apply()
branch = ensure("branch", "hr.department", {"name": "DEMO Guide Branch", "department_type": "branche"})
warehouse = ensure("warehouse", "stock.warehouse", {"name": "DEMO Guide Warehouse", "code": "GDE15", "branch_id": branch.id, "company_id": qa.company.id})
staff = ensure("staff", "hr.employee", {"name": "DEMO Guide Technician", "is_technician": True, "branch_id": branch.id})
customer = ensure("customer", "res.partner", {"name": "DEMO Guide Customer", "email": False, "mobile": False})
brand = ensure("car_brand", "fleet.vehicle.model.brand", {"name": "DEMO Guide Car"})
model = ensure("car_model", "fleet.vehicle.model", {"name": "DEMO Training Car", "brand_id": brand.id})
vehicle = ensure("vehicle", "fleet.vehicle", {"model_id": model.id, "license_plate": "DEMO-GUIDE"})
for key, product, qty in (("film_a_stock",film_a,2),("film_b_stock",film_b,2),("liquid_stock",liquid,10)):
    marker = "workorder_service_components.guide_demo_"+key
    if not qa.ref(marker, raise_if_not_found=False):
        quant = qa["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, qty)
        # Marker binds an existing dedicated stock location, not a financial record.
        qa["ir.model.data"].create({"module":"workorder_service_components", "name":"guide_demo_"+key,"model":"stock.location","res_id":warehouse.lot_stock_id.id,"noupdate":True})

def order(key, service):
    return ensure(key, "car.work.order", {"partner_id": customer.id, "vehicle_id": vehicle.id, "branch_id": branch.id, "company_id": qa.company.id, "notes": "DEMO ??? fictional screenshot example for the service material guide", "service_ids": [Command.create({"product_id": service.id, "staff_ids": [Command.set(staff.ids)]})]})

def prepare(record, product, selected_brand=False):
    if record.state == "new":
        for line in record.product_ids:
            line.write({"product_id":product.id, **({"material_brand_id":selected_brand.id} if selected_brand else {})})
        record.picking_id = record._create_delivery_picking()
        record.state = "confirmed"
        record.action_start_materials()

standard = order("order_standard", variants["Small"])
prepare(standard, film_a, marvel)
warning = order("order_warning", variants["Small"])
prepare(warning, film_a, marvel)
if warning.state == "progress":
    warning.product_ids[:1].actual_length_in = 21
issued = order("order_issued", variants["Small"])
prepare(issued, film_a, marvel)
if issued.state == "progress" and not issued.materials_finished:
    issued.action_finish_materials()
liquid_order = order("order_liquid", paint)
prepare(liquid_order, liquid)
result = {"database":qa.cr.dbname,"service_template":template.id,"variants":{k:v.id for k,v in variants.items()},"film_template":film_a.product_tmpl_id.id,"film":film_a.id,"alternative_film":film_b.id,"liquid_template":liquid.product_tmpl_id.id,"liquid_service_template":paint.product_tmpl_id.id,"liquid_service":paint.id,"batch":batch.id,"liquid_batch":liquid_batch.id,"part_configuration":variants["Small"].service_part_ids[:1].id,"order_standard":standard.id,"order_warning":warning.id,"order_issued":issued.id,"order_liquid":liquid_order.id,"delivery":issued.material_picking_ids.id,"warehouse":warehouse.id}
qa["ir.config_parameter"].sudo().set_param("workorder_service_components.guide_demo_ids",json.dumps(result))
qa.cr.commit()
print("MATERIAL_GUIDE_DEMO="+json.dumps(result,sort_keys=True))
