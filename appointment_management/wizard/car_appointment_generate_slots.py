from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CarAppointmentGenerateSlots(models.TransientModel):
    _name = "car.appointment.generate.slots"
    _description = "Car Appointment Generate Slots"

    branch_ids = fields.Many2many(
        'hr.department',
        'car_appointment_generate_slot_department_rel',
        'wizard_id', 'department_id',
        string='Branches',
        domain="[('department_type','=','branche')]",
        help='Branches concernées par la génération des créneaux.'
    )
    date_from = fields.Date()
    date_to = fields.Date()
    capacity = fields.Float(default=1, required=True)
    resource_calendar_id = fields.Many2one(
        "resource.calendar", default=lambda self: self.env.company.resource_calendar_id
    )
    duration = fields.Float("Slot Duration", default=1.0, required=True)

    def action_generate(self):
        """Method to generate appointment slots."""

        # Loop over the range of dates between date_from and date_to
        start_date = fields.Date.from_string(self.date_from)
        end_date = fields.Date.from_string(self.date_to)

        while start_date <= end_date:
            # Retrieve the working hours for the current date from the resource calendar
            calendar = self.resource_calendar_id
            working_hours = self._get_working_hours_for_day(
                calendar, start_date)

            # Check if the working hours were fetched properly
            if not working_hours:
                raise ValidationError(
                    _(
                        "Cannot generate slots for {date} — this day is either a weekend"
                        " or not defined in the calendar's working hours."
                        " Please check the calendar settings."
                    ).format(date=start_date.strftime("%d/%m/%Y"))
                )

            for start_time, end_time in working_hours:
                # Generate slots within the working hours
                current_start = start_time
                while current_start + self.duration <= end_time:
                    # Create the car appointment slot if no conflict exists (will be checked in the car.appointment.slot model)
                    slot_vals = {
                        "date": start_date,
                        "start_hour": current_start,
                        "duration": self.duration,
                        "capacity": self.capacity,
                        "is_available": True,
                    }
                    if self.branch_ids:
                        slot_vals["department_ids"] = [
                            (6, 0, self.branch_ids.ids)]
                    self.env["car.appointment.slot"].create(slot_vals)
                    current_start += self.duration  # Move to the next slot

            start_date += timedelta(days=1)  # Move to the next day
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def _get_working_hours_for_day(self, calendar, date):
        """Returns working hours for the given date using the resource calendar's attendance records."""
        working_hours = []

        # Get the day of the week (0 = Monday, 6 = Sunday)
        day_of_week = date.weekday()

        # Find the attendance records for the corresponding day of the week
        attendance_records = self.env["resource.calendar.attendance"].search(
            [
                ("calendar_id", "=", calendar.id),
                ("dayofweek", "=", day_of_week),
            ]
        )

        # Extract start and end times from attendance records
        for attendance in attendance_records:
            working_hours.append((attendance.hour_from, attendance.hour_to))

        return working_hours

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        """Ensure that 'date_tTransientModelo' is not before 'date_from'."""
        for record in self:
            if record.date_from and record.date_to:
                if fields.Date.from_string(record.date_to) < fields.Date.from_string(record.date_from):
                    raise ValidationError(
                        _("'Date from' must be before 'Date to'."))
            if fields.Date.from_string(record.date_from) < fields.Date.today():
                raise ValidationError(_("'Date from' cannot be in the past."))
