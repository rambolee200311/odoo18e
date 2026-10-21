# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class BlindStockCountCancelPickingBatch(models.Model):
    _name = "blind.stock.count.cancel.picking.batch"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count Cancel Picking Batch"
    _order = "id desc"

    name = fields.Char(string="Cancellation Batch Number", required=True, readonly=True, copy=False, index=True, default=lambda self: self.env["ir.sequence"].next_by_code("blind.stock.count.cancel.picking.batch") or _("New"))
    work_package_id = fields.Many2one("blind.stock.count.work.package", string="Work Package", required=True, readonly=True, ondelete="restrict", copy=False, index=True)
    requested_by_id = fields.Many2one("res.users", string="Requested By", required=True, readonly=True, default=lambda self: self.env.user, copy=False, index=True)
    requested_at = fields.Datetime(string="Requested At", required=True, readonly=True, default=fields.Datetime.now, copy=False, index=True)
    picking_lines = fields.One2many("blind.stock.count.cancel.picking.batch.line", "cancel_picking_batch_id", string="Picking Lines", readonly=True, copy=False)
    total_count = fields.Integer(string="Total", compute="_compute_progress", store=True)
    pending_count = fields.Integer(string="Queued", compute="_compute_progress", store=True)
    cancelled_count = fields.Integer(string="Cancelled", compute="_compute_progress", store=True)
    skipped_count = fields.Integer(string="Skipped", compute="_compute_progress", store=True)
    failed_count = fields.Integer(string="Failed", compute="_compute_progress", store=True)
    state = fields.Selection([("queued", "Queued"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")], string="Status", compute="_compute_progress", store=True, readonly=True, copy=False, index=True, tracking=True)

    @api.depends("picking_lines.state")
    def _compute_progress(self):
        for rec in self:
            states = rec.picking_lines.mapped("state")
            rec.total_count = len(states)
            rec.pending_count = states.count("queued")
            rec.cancelled_count = states.count("cancelled")
            rec.skipped_count = states.count("skipped")
            rec.failed_count = states.count("failed")
            if "running" in states:
                rec.state = "running"
            elif "queued" in states:
                rec.state = "queued"
            elif "failed" in states:
                rec.state = "failed"
            else:
                rec.state = "done"


class BlindStockCountCancelPickingBatchLine(models.Model):
    _name = "blind.stock.count.cancel.picking.batch.line"
    _description = "Blind Stock Count Cancel Picking Batch Line"
    _order = "id desc"
    _sql_constraints = [("blind_stock_count_cancel_picking_batch_line_unique", "unique(cancel_picking_batch_id, picking_id)", "A picking can only be queued once in the same cancellation batch.")]

    cancel_picking_batch_id = fields.Many2one("blind.stock.count.cancel.picking.batch", string="Cancellation Batch", required=True, readonly=True, ondelete="cascade", copy=False, index=True)
    picking_id = fields.Many2one("stock.picking", string="Picking", required=True, readonly=True, ondelete="restrict", copy=False, index=True)
    picking_name = fields.Char(string="Picking Number", required=True, readonly=True, copy=False, index=True)
    state_before = fields.Char(string="State Before Cancellation", required=True, readonly=True, copy=False)
    picking_type_id = fields.Many2one("stock.picking.type", string="Operation Type", readonly=True, copy=False, index=True)
    source_location_id = fields.Many2one("stock.location", string="Source Location", readonly=True, copy=False, index=True)
    destination_location_id = fields.Many2one("stock.location", string="Destination Location", readonly=True, copy=False, index=True)
    state = fields.Selection([("queued", "Queued"), ("running", "Running"), ("cancelled", "Cancelled"), ("skipped", "Skipped"), ("failed", "Failed")], string="Status", required=True, readonly=True, default="queued", copy=False, index=True)
    queue_job_id = fields.Many2one("queue.job", string="Queue Job", readonly=True, ondelete="set null", copy=False, index=True)
    processed_at = fields.Datetime(string="Processed At", readonly=True, copy=False, index=True)
    error_message = fields.Text(string="Error Message", readonly=True, copy=False)

    def job_cancel_pickings(self):
        log_model = self.env["blind.stock.count.cancelled.picking.log"]
        picking_model = self.env["stock.picking"]
        batch_lines = self.filtered(lambda rec: rec.state == "queued")
        if not batch_lines:
            return True
        work_packages = batch_lines.mapped("cancel_picking_batch_id.work_package_id")
        if len(work_packages) != 1:
            for rec in batch_lines:
                rec.write({"state": "failed", "processed_at": fields.Datetime.now(), "error_message": _("A cancellation job can only process one work package.")})
            return False
        work_package = work_packages
        if work_package.state != "done" or picking_model.sudo().search_count([("blind_stock_count_work_package_id", "=", work_package.id), ("is_blind_stock_count_clearance", "=", True), ("state", "not in", ["done", "cancel"])]):
            message = _("The work package is no longer eligible for pending picking cancellation.")
            for rec in batch_lines:
                rec.write({"state": "skipped", "processed_at": fields.Datetime.now(), "error_message": message})
            return True
        cancelable_picking_ids = set(work_package.get_cancelable_pending_pickings().ids)
        for rec in batch_lines:
            rec.write({"state": "running"})
            try:
                with self.env.cr.savepoint():
                    picking = rec.picking_id
                    picking.invalidate_recordset(["state"])
                    picking.move_ids.invalidate_recordset(["state"])
                    active_moves = picking.move_ids.filtered(lambda move: move.state != "cancel")
                    if picking.id not in cancelable_picking_ids or picking.state == "cancel" or not active_moves or active_moves.filtered(lambda move: move.state == "done"):
                        rec.write({"state": "skipped", "processed_at": fields.Datetime.now(), "error_message": _("Picking is no longer eligible for cancellation.")})
                        continue
                    picking.action_cancel()
                    picking.invalidate_recordset(["state"])
                    if picking.state != "cancel":
                        rec.write({"state": "failed", "processed_at": fields.Datetime.now(), "error_message": _("Picking %s could not be cancelled.") % picking.display_name})
                        continue
                    log_model.create({"work_package_id": work_package.id, "picking_id": picking.id, "picking_name": picking.name, "state_before": rec.state_before, "picking_type_id": picking.picking_type_id.id, "source_location_id": picking.location_id.id, "destination_location_id": picking.location_dest_id.id, "cancelled_by_id": rec.cancel_picking_batch_id.requested_by_id.id, "cancelled_at": fields.Datetime.now(), "reason": _("Blind stock count clearance")})
                    picking.message_post(body=_("Cancelled by blind stock count work package %s for clearance.") % work_package.display_name)
                    rec.write({"state": "cancelled", "processed_at": fields.Datetime.now(), "error_message": False})
            except Exception as error:
                rec.write({"state": "failed", "processed_at": fields.Datetime.now(), "error_message": str(error)})
        return True
