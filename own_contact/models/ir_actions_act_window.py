from odoo import models


class IrActionsActWindow(models.Model):
    _inherit = "ir.actions.act_window"

    def read(self, fields=None, load="_classic_read"):
        actions = super().read(fields=fields, load=load)
        # /web/action/load reads actions with sudo(), but keeps the session user.
        # Filter the contact screen without restricting internal partner lookups.
        user = self.env.user
        if user.has_group("own_contact.group_own_contact") and not user.has_group(
            "own_contact.group_all_contacts"
        ):
            for action in actions:
                if "domain" not in action:
                    continue
                model = action.get("res_model") or self.browse(action["id"]).res_model
                if model != "res.partner":
                    continue
                domain = action["domain"] or "[]"
                # Keep existing action domains (including their client-side
                # variables); concatenation adds an implicit AND restriction.
                action["domain"] = "[('user_id', '=', %d)] + (%s)" % (
                    user.id, domain,
                )
        return actions
