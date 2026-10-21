# -*- coding: utf-8 -*-

import os

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    is_blind_stock_count_clearance = fields.Boolean(string="Blind Stock Count Clearance", copy=False, index=True)
    is_blind_stock_count_receipt = fields.Boolean(string="Blind Stock Count Receipt", copy=False, index=True)
    blind_stock_count_work_package_id = fields.Many2one("blind.stock.count.work.package", string="Blind Stock Count Work Package", readonly=True, copy=False, index=True)
    blind_stock_count_id = fields.Many2one("blind.stock.count", string="Blind Stock Count", readonly=True, copy=False, index=True)
    blind_stock_count_clearance_batch_id = fields.Many2one("blind.stock.count.clearance.batch", string="Clearance Batch", readonly=True, copy=False, index=True)
    blind_stock_count_validation_state = fields.Selection([("queued", "Queued"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")], string="Blind Stock Count Validation Status", readonly=True, copy=False, index=True)
    blind_stock_count_validation_error = fields.Text(string="Blind Stock Count Validation Error", readonly=True, copy=False)
    blind_stock_count_validation_queue_job_id = fields.Many2one("queue.job", string="Blind Stock Count Validation Queue Job", readonly=True, ondelete="set null", copy=False, index=True)

    def button_validate(self):
        if self.env.context.get("blind_stock_count_clearance_validation") or self.env.context.get("blind_stock_count_queue_validation"):
            return super().button_validate()
        blind_stock_count_pickings = self.filtered(lambda picking: picking.is_blind_stock_count_clearance or picking.is_blind_stock_count_receipt)
        other_pickings = self - blind_stock_count_pickings
        result = True
        if blind_stock_count_pickings:
            result = blind_stock_count_pickings.action_queue_validate_blind_stock_count_pickings()
        if other_pickings:
            result = other_pickings.button_validate()
        return result

    def action_queue_validate_blind_stock_count_pickings(self):
        if not self:
            raise UserError(_("Select at least one blind stock count picking to validate."))
        if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
            raise UserError(_("Only a warehouse manager or system administrator can validate blind stock count pickings."))
        invalid_pickings = self.filtered(lambda rec: not (rec.is_blind_stock_count_clearance or rec.is_blind_stock_count_receipt) or rec.state in ("done", "cancel"))
        if invalid_pickings:
            raise UserError(_("Select only unvalidated blind stock count inbound or clearance pickings."))
        queued_pickings = self.filtered(lambda rec: rec.blind_stock_count_validation_state in ("queued", "running"))
        if queued_pickings:
            raise UserError(_("Picking %s already has a validation task in progress.") % queued_pickings[0].display_name)
        if os.getenv("QUEUE_JOB__NO_DELAY") or self.env.context.get("queue_job__no_delay"):
            raise UserError(_("Queue workers must be enabled before submitting picking validation tasks."))
        for index in range(0, len(self), 50):
            pickings = self[index:index + 50]
            job = pickings.with_delay(description=_("Validate blind stock count pickings"), identity_key="blind_stock_count_validation:%s" % ",".join(str(picking_id) for picking_id in pickings.ids), channel="root.blind_stock_count").job_validate_blind_stock_count_pickings()
            queue_job = job.db_record() if job and hasattr(job, "db_record") else self.env["queue.job"]
            vals = {"blind_stock_count_validation_state": "queued", "blind_stock_count_validation_error": False}
            if queue_job:
                vals["blind_stock_count_validation_queue_job_id"] = queue_job.id
            pickings.write(vals)
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"type": "success", "message": _("Picking validation task(s) were queued."), "sticky": False}}

    def job_validate_blind_stock_count_pickings(self):
        for rec in self:
            if rec.state == "done":
                rec.write({"blind_stock_count_validation_state": "done", "blind_stock_count_validation_error": False})
                continue
            if rec.state == "cancel":
                rec.write({"blind_stock_count_validation_state": "failed", "blind_stock_count_validation_error": _("The picking was cancelled before validation.")})
                continue
            rec.write({"blind_stock_count_validation_state": "running", "blind_stock_count_validation_error": False})
            try:
                with self.env.cr.savepoint():
                    context = {"skip_backorder": True}
                    if rec.is_blind_stock_count_clearance:
                        context.update({"blind_stock_count_clearance_validation": True, "skip_sanity_check": True})
                    else:
                        context["blind_stock_count_queue_validation"] = True
                    rec.with_context(**context).button_validate()
                    rec.invalidate_recordset(["state"])
                    if rec.state != "done":
                        raise UserError(_("The picking was not completed by validation."))
                rec.write({"blind_stock_count_validation_state": "done", "blind_stock_count_validation_error": False})
            except Exception as error:
                rec.write({"blind_stock_count_validation_state": "failed", "blind_stock_count_validation_error": str(error)})
        return True

    def action_cancel_blind_stock_count_pending_pickings(self):
        cancel_picking_batch_model = self.env["blind.stock.count.cancel.picking.batch"]
        cancel_picking_batch_line_model = self.env["blind.stock.count.cancel.picking.batch.line"]
        picking_model = self.env["stock.picking"]
        work_package_model = self.env["blind.stock.count.work.package"]
        work_package_id = self.env.context.get("blind_stock_count_cancel_work_package_id")
        if not work_package_id:
            raise UserError(_("Open the pending picking list from a work package before cancelling pickings."))
        if not self:
            raise UserError(_("Select at least one picking to cancel."))
        if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
            raise UserError(_("Only a warehouse manager or system administrator can cancel pending pickings."))
        work_package = work_package_model.sudo().browse(work_package_id).exists()
        if not work_package or work_package.state != "done":
            raise UserError(_("Pending pickings can only be cancelled from a completed work package."))
        if picking_model.sudo().search([("blind_stock_count_work_package_id", "=", work_package.id), ("is_blind_stock_count_clearance", "=", True), ("state", "not in", ["done", "cancel"])], limit=1):
            raise UserError(_("Pending pickings cannot be cancelled while clearance outbound pickings are still in progress."))
        cancelable_picking_ids = set(work_package.get_cancelable_pending_pickings().ids)
        if any(picking.id not in cancelable_picking_ids for picking in self):
            raise UserError(_("Selected pickings must match the current work package category and location scope."))
        queued_line = cancel_picking_batch_line_model.sudo().search([("picking_id", "in", self.ids), ("state", "in", ["queued", "running"])], limit=1)
        if queued_line:
            raise UserError(_("Picking %s is already in cancellation batch %s.") % (queued_line.picking_name, queued_line.cancel_picking_batch_id.name))
        if os.getenv("QUEUE_JOB__NO_DELAY") or self.env.context.get("queue_job__no_delay"):
            raise UserError(_("Queue workers must be enabled before submitting picking cancellation tasks."))
        batch = cancel_picking_batch_model.create({"work_package_id": work_package.id})
        lines = cancel_picking_batch_line_model.create([{"cancel_picking_batch_id": batch.id, "picking_id": rec.id, "picking_name": rec.name, "state_before": rec.state, "picking_type_id": rec.picking_type_id.id, "source_location_id": rec.location_id.id, "destination_location_id": rec.location_dest_id.id} for rec in self])
        for index in range(0, len(lines), 50):
            batch_lines = lines[index:index + 50]
            job = batch_lines.with_delay(description=_("Cancel pending pickings for %s") % work_package.display_name, identity_key="blind_stock_count_cancel_picking:%s:%s" % (batch.id, index // 50), channel="root.blind_stock_count").job_cancel_pickings()
            queue_job = job.db_record() if job and hasattr(job, "db_record") else self.env["queue.job"]
            if queue_job:
                batch_lines.write({"queue_job_id": queue_job.id})
        return {"type": "ir.actions.act_window", "name": _("Cancellation Batch"), "res_model": "blind.stock.count.cancel.picking.batch", "view_mode": "form", "res_id": batch.id, "target": "current"}
