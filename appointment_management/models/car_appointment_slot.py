from datetime import datetime

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CarAppointmentSlot(models.Model):
    _name = "car.appointment.slot"
    _description = "Car Appointment Slot"
    _rec_name = "start_date"

    date = fields.Date()
    start_hour = fields.Float(
        "Starting Hour", required=True, group_operator=None)
    duration = fields.Float(required=True, group_operator=None)
    finish_hour = fields.Float(
        "Finishing Hour", compute="_compute_dates", store=True, group_operator=None)
    start_date = fields.Datetime(compute="_compute_dates", store=True)
    finish_date = fields.Datetime(compute="_compute_dates", store=True)
    capacity = fields.Float(required=True)
    is_available = fields.Boolean()
    car_appointment_ids = fields.One2many(
        "car.appointment", "appointment_slot_id", string="Appointments")
    car_appointment_count = fields.Integer(
        compute="_compute_car_appointment_count", string="Appointments number")
    company_id = fields.Many2one(
        "res.company", string="Agency", default=lambda self: self.env.company, required=True)
    department_ids = fields.Many2many(
        'hr.department',
        'car_appointment_slot_department_rel',
        'slot_id', 'department_id',
        string='Branches',
        help='Branches (departments) associated with this slot',
    )
    calendar_color = fields.Integer(
        string="Color", compute="_compute_is_available")

    @api.constrains("date", "start_hour", "duration")
    def _check_no_conflict(self):
        """Ensure that the appointment slot does not conflict with any existing slots."""
        for slot in self:
            conflicting_slots = self.env["car.appointment.slot"].search(
                [
                    ("id", "!=", slot.id),
                    ("company_id", "=", self.env.company.id),
                    ("date", "=", slot.date),
                    ("start_hour", ">=", slot.start_hour),
                    ("finish_hour", "<=", slot.finish_hour),
                ]
            )

            if conflicting_slots:
                raise ValidationError(
                    _("Appointment slot on {slot_date} at {start_hour} conflicts with an existing appointment.").format(
                        slot_date=slot.date, start_hour=slot.start_hour
                    )
                )

    @api.depends("date", "start_hour", "duration")
    def _compute_dates(self):
        for slot in self:
            if slot.date and slot.start_hour is not None and slot.duration is not None:
                # Convert date to datetime object
                slot_date = datetime.combine(slot.date, datetime.min.time())
                start_datetime = slot_date + \
                    relativedelta(hours=slot.start_hour)
                finish_datetime = slot_date + \
                    relativedelta(hours=slot.start_hour + slot.duration)

                # Set computed values to the fields
                tz_session = pytz.timezone(self.env.user.tz or "UTC")
                start_datetime = tz_session.localize(
                    start_datetime).astimezone(pytz.utc).replace(tzinfo=None)
                finish_datetime = tz_session.localize(
                    finish_datetime).astimezone(pytz.utc).replace(tzinfo=None)

                slot.start_date = start_datetime
                slot.finish_date = finish_datetime
                slot.finish_hour = slot.start_hour + slot.duration
            else:
                slot.start_date = False
                slot.finish_date = False
                slot.finish_hour = 0

    @api.depends("date", "start_hour", "duration")
    def _compute_is_available(self):
        for slot in self:
            # calendar_color: 10 (green), 1 (red)
            if len(slot.car_appointment_ids) < slot.capacity:
                slot.is_available = True
                slot.calendar_color = 10
            else:
                slot.is_available = False
                slot.calendar_color = 1

    @api.depends("car_appointment_ids")
    def _compute_car_appointment_count(self):
        for slot in self:
            slot.car_appointment_count = len(slot.car_appointment_ids)
