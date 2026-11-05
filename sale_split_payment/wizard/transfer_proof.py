from odoo import _, Command, fields, models
from odoo.exceptions import UserError


def check_upload(proofs, journal):
    if journal.type == "bank" and not proofs:
        raise UserError(_("Upload transfer proof before confirming a bank payment."))
    proofs.check("read")


class PaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    transfer_proof_ids = fields.Many2many("ir.attachment", string="Transfer Proof")
    journal_type = fields.Selection(related="journal_id.type")

    def _create_payment_vals_from_wizard(self, batch_result):
        values = super()._create_payment_vals_from_wizard(batch_result)
        values["transfer_proof_ids"] = [Command.set(self.transfer_proof_ids.ids)]
        return values

    def _create_payment_vals_from_batch(self, batch_result):
        values = super()._create_payment_vals_from_batch(batch_result)
        values["transfer_proof_ids"] = [Command.set(self.transfer_proof_ids.ids)]
        return values

    def _create_payments(self):
        self.ensure_one()
        check_upload(self.transfer_proof_ids, self.journal_id)
        return super()._create_payments()


class CollectSingle(models.TransientModel):
    _inherit = "sale.split.payment.wizard"

    transfer_proof_ids = fields.Many2many("ir.attachment", string="Transfer Proof")
    journal_type = fields.Selection(related="journal_id.type")

    def action_collect_payment(self):
        self.ensure_one()
        if self.processing_type == "manual":
            check_upload(self.transfer_proof_ids, self.journal_id or self.collection_method_id.resolve_journal())
        else:
            self.transfer_proof_ids.check("read")
        return super(CollectSingle, self.with_context(
            default_transfer_proof_ids=[Command.set(self.transfer_proof_ids.ids)]
        )).action_collect_payment()


class CollectMultiple(models.TransientModel):
    _inherit = "sale.multi.split.payment.wizard"

    transfer_proof_ids = fields.Many2many("ir.attachment", string="Transfer Proof")
    journal_type = fields.Selection(related="journal_id.type")

    def action_collect_payment(self):
        self.ensure_one()
        check_upload(self.transfer_proof_ids, self.journal_id or self.collection_method_id.resolve_journal())
        return super(CollectMultiple, self.with_context(
            default_transfer_proof_ids=[Command.set(self.transfer_proof_ids.ids)],
            default_cash_collector_user_id=self.env.uid,
        )).action_collect_payment()
