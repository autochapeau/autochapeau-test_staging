"""Isolated fictional operations tutorial, TEST only; never alters live recipes."""
import json
from odoo import Command, fields

assert env.cr.dbname == 'autochapeau_prod_test'
op = env(context=dict(env.context, tracking_disable=True, mail_create_nosubscribe=True,
                      mail_notrack=True, no_reset_password=True))

def fixture(key, model, values):
    name = 'operations_video_20261116_' + key
    record = op.ref('workorder_service_components.' + name, raise_if_not_found=False)
    if record and record.exists():
        assert record._name == model
        return record
    record = op[model].create(values)
    op['ir.model.data'].create({'module': 'workorder_service_components', 'name': name,
                              'model': model, 'res_id': record.id, 'noupdate': True})
    return record

branch = op['hr.department'].search([('name', '=', 'DEMO Guide Branch')], limit=1)
warehouse = op['stock.warehouse'].search([('branch_id', '=', branch.id)], limit=1)
staff = op['hr.employee'].search([('name', '=', 'DEMO Guide Technician'), ('branch_id', '=', branch.id)], limit=1)
assert branch and warehouse and staff
customer = fixture('customer', 'res.partner', {'name': 'DEMO Operations Customer', 'phone': False, 'mobile': False, 'email': False})
assert not (customer.phone or customer.mobile or customer.email)
vehicle_model = op['fleet.vehicle.model'].search([('name', '=', 'DEMO Training Car')], limit=1)
assert vehicle_model
vehicle = fixture('vehicle', 'fleet.vehicle', {'model_id': vehicle_model.id, 'vin_sn': 'DEMOOPS261116'})
attribute = op.ref('workorder_service_components.guide_demo_size')
values = attribute.value_ids.filtered(lambda value: value.name in ['Small', 'Medium', 'Large', 'XL'])
assert len(values) == 4
service = fixture('service', 'product.template', {'name': 'DEMO Operations | Window Tinting', 'detailed_type': 'service', 'list_price': 0,
    'attribute_line_ids': [Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(values.ids)]})]})
slot = fixture('slot', 'car.appointment.slot', {'company_id': warehouse.company_id.id,
    'date': fields.Date.add(fields.Date.today(), days=1), 'start_hour': 6.125,
    'duration': .25, 'capacity': 1, 'department_ids': [Command.set(branch.ids)]})
# This is an explicitly completed fictional reception prerequisite. The video
# records adding the service, confirming and starting the actual new work order.
checkin = fixture('checkin', 'car.checkin', {'partner_id': customer.id, 'vehicle_id': vehicle.id,
    'company_id': warehouse.company_id.id, 'branch_id': branch.id, 'state': 'done',
    'date': fields.Datetime.now(), 'notes': 'DEMO ONLY completed reception prerequisite for operations video', 'car_check_item_ids': []})
appointment = fixture('appointment', 'car.appointment', {'partner_id': customer.id, 'vehicle_id': vehicle.id,
    'company_id': warehouse.company_id.id, 'branch_id': branch.id, 'appointment_slot_id': slot.id,
    'car_checkin_id': checkin.id, 'state': 'confirmed'})
order = fixture('order', 'car.work.order', {'partner_id': customer.id, 'vehicle_id': vehicle.id,
    'company_id': warehouse.company_id.id, 'branch_id': branch.id, 'appointment_id': appointment.id,
    'notes': 'DEMO Operations 20261116 | Practical workshop training only'})
result = {'template': service.id, 'variants': {p.product_template_attribute_value_ids.product_attribute_value_id.name: p.id for p in service.product_variant_ids},
    'order': order.id, 'order_name': order.name, 'checkin': checkin.id, 'customer': customer.id, 'vehicle': vehicle.id,
    'staff': staff.id, 'branch': branch.id, 'warehouse': warehouse.id}
op['ir.config_parameter'].sudo().set_param('workorder_service_components.operations_video_ids', json.dumps(result))
op.cr.commit()
print('OPERATIONS_VIDEO_FIXTURE=' + json.dumps(result, sort_keys=True))
