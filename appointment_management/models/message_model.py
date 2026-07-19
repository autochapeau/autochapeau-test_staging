from odoo import _, api, models


class MessageModel(models.Model):
    _inherit = "message.model"

    @api.model
    def open_form_with_car_appointment(self):
        """Open message model form for car appointments."""
        model = self.env["ir.model"]._get("car.appointment")
        return {
            "type": "ir.actions.act_window",
            "name": _("Message Models"),
            "res_model": "message.model",
            "view_mode": "tree,form",
            "target": "current",
            "domain": [("model_ids", "in", [model.id])],
            "context": {
                "default_model_ids": [model.id] if model else [],
            },
        }
