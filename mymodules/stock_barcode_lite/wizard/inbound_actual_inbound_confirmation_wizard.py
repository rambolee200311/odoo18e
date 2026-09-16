# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class InboundActualInboundConfirmationWizard(models.TransientModel):
    _name = "inbound.actual.inbound.confirmation.wizard"
    _description = "Inbound Actual Inbound Confirmation Wizard"
    _order = "id desc"

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", required=True, readonly=True, index=True, copy=False)
    actual_inbound_datetime = fields.Datetime(string="Actual Inbound Time", default=fields.Datetime.now, copy=False)
    confirmed_by_id = fields.Many2one("res.users", string="Confirmed By", required=True, default=lambda self: self.env.user, readonly=True, index=True, copy=False)
    actual_inbound_attachment_line_ids = fields.Many2many("ir.attachment", "stock_barcode_lite_actual_inbound_wizard_attachment_rel", "wizard_id", "attachment_id", string="Photos", copy=False)

    def action_confirm_actual_inbound(self):
        for rec in self:
            inbound_order = rec.inbound_order_id
            if inbound_order.state != "confirm":
                raise UserError(_("Only confirmed inbound orders can confirm actual inbound."))
            if inbound_order.project_stock_report_date_mode != "business":
                raise UserError(_("Actual inbound confirmation is available only for projects using Order Business Date."))
            if not rec.actual_inbound_datetime:
                raise UserError(_("Actual inbound time is required."))
            actual_inbound_date = fields.Datetime.context_timestamp(rec, rec.actual_inbound_datetime).date()
            confirmation_datetime = fields.Datetime.now()
            previous_attachment_line_ids = inbound_order.actual_inbound_attachment_line_ids
            attachment_line_ids = rec.actual_inbound_attachment_line_ids
            removed_attachment_line_ids = previous_attachment_line_ids - attachment_line_ids
            inbound_order.write({
                "actual_inbound_datetime": rec.actual_inbound_datetime,
                "actual_inbound_date": actual_inbound_date,
                "actual_inbound_confirmed_by_id": self.env.user.id,
                "actual_inbound_confirmation_datetime": confirmation_datetime,
                "actual_inbound_attachment_line_ids": [(6, 0, attachment_line_ids.ids)],
            })
            if removed_attachment_line_ids:
                removed_attachment_line_ids.unlink()
        return {"type": "ir.actions.act_window_close"}
