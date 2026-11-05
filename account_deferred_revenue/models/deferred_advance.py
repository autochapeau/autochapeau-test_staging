from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class Journal(models.Model):
    _inherit = "account.journal"

    service_advance_account_id = fields.Many2one(
        "account.account", string="Deferred Revenue Account", check_company=True,
        domain="[('company_id', '=', company_id), ('account_type', '=', 'liability_current'), ('deprecated', '=', False)]",
        help="Liability for invoices issued before the service. Cleared by the final service invoice.")

    @api.constrains("service_advance_account_id", "type")
    def _check_service_advance_account(self):
        for journal in self.filtered("service_advance_account_id"):
            if journal.type != "sale" or journal.service_advance_account_id.account_type != "liability_current" or journal.service_advance_account_id.deprecated:
                raise ValidationError(_("Deferred service revenue requires an active current liability account on a sales journal."))


class SaleLine(models.Model):
    _inherit = "sale.order.line"

    service_advance_account_id = fields.Many2one("account.account", copy=False, check_company=True, readonly=True)

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)
        if self.service_advance_account_id and not self.display_type:
            # Retain the original liability even if the journal configuration changes.
            values.update(account_id=self.service_advance_account_id.id, is_service_advance=True)
        return values


class InvoiceLine(models.Model):
    _inherit = "account.move.line"

    is_service_advance = fields.Boolean(string="Deferred Service Advance", copy=True, readonly=True)

    def _is_deferred_revenue_line(self):
        return not self.is_service_advance and super()._is_deferred_revenue_line()

    def _copy_data_extend_business_fields(self, values):
        super()._copy_data_extend_business_fields(values)
        values["is_service_advance"] = self.is_service_advance


class AdvanceWizard(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    advance_payment_method = fields.Selection(
        selection_add=[("deferred_service", "Deferred Revenue")],
        ondelete={"deferred_service": "set default"})
    service_advance_journal_id = fields.Many2one(
        "account.journal", string="Sales Journal", check_company=True,
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]")

    def _create_invoices(self, sale_orders):
        self.ensure_one()
        if self.advance_payment_method != "deferred_service":
            return super()._create_invoices(sale_orders)
        sale_orders.ensure_one()
        journal = self.service_advance_journal_id
        if not journal or journal.company_id != sale_orders.company_id or journal.type != "sale" or not journal.service_advance_account_id:
            raise UserError(_("Select a sales journal with a Deferred Revenue Account before creating the invoice."))
        if self.fixed_amount <= 0:
            raise UserError(_("The deferred invoice amount must be positive."))
        # Serialize advances from multiple sessions and include existing drafts.
        self.env.cr.execute("SELECT id FROM sale_order WHERE id = %s FOR UPDATE", [sale_orders.id])
        sale_orders.invalidate_recordset()
        # Invoice totals use the order currency, including existing draft advances.
        invoiced = sum(move.amount_total * (-1 if move.move_type == "out_refund" else 1)
                       for move in sale_orders.invoice_ids if move.state != "cancel")
        if sale_orders.currency_id.compare_amounts(self.fixed_amount, sale_orders.amount_total - invoiced) > 0:
            raise UserError(_("The deferred invoice exceeds the order's remaining uninvoiced amount."))
        # Reuse Odoo's tax grouping, inclusive-tax rounding and final deduction logic.
        # A second transient keeps the user's selected option intact throughout.
        core_wizard = self.copy({"advance_payment_method": "fixed"})
        return super(AdvanceWizard, core_wizard.with_context(deferred_service_advance=True))._create_invoices(sale_orders)

    def _prepare_base_downpayment_line_values(self, order):
        values = super()._prepare_base_downpayment_line_values(order)
        if self.env.context.get("deferred_service_advance"):
            values.update(service_advance_account_id=self.service_advance_journal_id.service_advance_account_id.id,
                          name=_("Deferred Service Advance"))
        return values

    def _prepare_invoice_values(self, order, so_lines):
        values = super()._prepare_invoice_values(order, so_lines)
        if self.env.context.get("deferred_service_advance"):
            values["journal_id"] = self.service_advance_journal_id.id
        return values

    def _get_down_payment_description(self, order):
        if self.env.context.get("deferred_service_advance"):
            return _("Deferred Service Advance")
        return super()._get_down_payment_description(order)
