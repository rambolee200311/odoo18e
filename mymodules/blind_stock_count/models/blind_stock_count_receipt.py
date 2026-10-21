# -*- coding: utf-8 -*-

import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BlindStockCount(models.Model):
    _inherit = "blind.stock.count"

    inbound_picking_lines = fields.One2many("stock.picking", "blind_stock_count_id", string="Inbound Pickings", domain=[("is_blind_stock_count_receipt", "=", True)], copy=False)
    receipt_generation_state = fields.Selection([("queued", "Queued"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")], string="Inbound Generation Status", readonly=True, copy=False, index=True)
    receipt_picking_state = fields.Selection([("not_created", "Not Created"), ("queued", "Queued"), ("running", "Running"), ("failed", "Failed"), ("draft", "Draft"), ("waiting", "Waiting Another Operation"), ("confirmed", "Waiting"), ("assigned", "Ready"), ("done", "Done"), ("cancel", "Cancelled")], string="Inbound Picking Status", compute="compute_receipt_picking_state")
    receipt_generation_error = fields.Text(string="Inbound Generation Error", readonly=True, copy=False)
    receipt_queue_job_id = fields.Many2one("queue.job", string="Inbound Queue Job", readonly=True, ondelete="set null", copy=False, index=True)

    @api.depends("receipt_generation_state", "inbound_picking_lines.state")
    def compute_receipt_picking_state(self):
        picking_records = self.env["stock.picking"].sudo().search([("blind_stock_count_id", "in", self.ids), ("is_blind_stock_count_receipt", "=", True)], order="id desc")
        picking_by_count = {}
        for picking in picking_records:
            picking_by_count.setdefault(picking.blind_stock_count_id.id, picking)
        for rec in self:
            picking = picking_by_count.get(rec.id)
            if picking:
                rec.receipt_picking_state = picking.state
            elif rec.receipt_generation_state in ("queued", "running", "failed"):
                rec.receipt_picking_state = rec.receipt_generation_state
            else:
                rec.receipt_picking_state = "not_created"

    def action_create_receipt(self):
        count_model = self.env["blind.stock.count"]
        picking_model = self.env["stock.picking"]
        if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
            raise UserError(_("Only a warehouse manager or system administrator can generate inbound pickings."))
        for rec in self:
            if rec.state != "done" or rec.is_replaced:
                raise UserError(_("Only the current completed blind stock count can generate an inbound picking."))
            if rec.work_package_id.state not in ("in_progress", "done"):
                raise UserError(_("The work package must be in progress or completed before generating an inbound picking."))
            if not rec.work_package_id.receipt_picking_type_id or rec.work_package_id.receipt_picking_type_id.code != "incoming":
                raise UserError(_("Select a receipt inbound operation type on the work package before generating an inbound picking."))
            if not rec.work_package_id.receipt_source_location_id:
                raise UserError(_("Select a receipt source location on the work package before generating an inbound picking."))
            if count_model.sudo().search_count([("recounted_from_id", "=", rec.id), ("state", "!=", "cancel")]):
                raise UserError(_("Cancel the active recount before generating an inbound picking."))
            if picking_model.sudo().search_count([("blind_stock_count_id", "=", rec.id), ("is_blind_stock_count_receipt", "=", True), ("state", "!=", "cancel")]):
                raise UserError(_("An active inbound picking already exists for this blind stock count."))
            clearance_pickings = picking_model.sudo().search([("blind_stock_count_work_package_id", "=", rec.work_package_id.id), ("is_blind_stock_count_clearance", "=", True), ("state", "!=", "cancel")], order="id desc")
            if not clearance_pickings:
                raise UserError(_("Generate clearance pickings for this work package before generating an inbound picking."))
            if clearance_pickings.filtered(lambda picking: picking.state != "done"):
                raise UserError(_("Complete every clearance outbound picking before generating an inbound picking."))
            if rec.receipt_generation_state in ("queued", "running"):
                raise UserError(_("An inbound picking generation task is already queued or running for %s.") % rec.name)
        if os.getenv("QUEUE_JOB__NO_DELAY") or self.env.context.get("queue_job__no_delay"):
            raise UserError(_("Queue workers must be enabled before submitting inbound picking generation tasks."))
        for rec in self:
            job = rec.with_delay(description=_("Generate inbound picking for %s") % rec.name, identity_key="blind_stock_count_receipt:%s" % rec.id, channel="root.blind_stock_count").job_create_inbound_picking()
            queue_job = job.db_record() if job and hasattr(job, "db_record") else self.env["queue.job"]
            vals = {"receipt_generation_state": "queued", "receipt_generation_error": False}
            if queue_job:
                vals["receipt_queue_job_id"] = queue_job.id
            rec.with_context(blind_stock_count_receipt_queue_action=True).write(vals)
            rec.message_post(body=_("Inbound picking generation was queued."))
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"type": "success", "message": _("Inbound picking generation task(s) were queued."), "sticky": False}}

    def action_batch_create_receipt_pickings(self):
        return self.action_create_receipt()

    def action_batch_validate_receipt_pickings(self):
        picking_model = self.env["stock.picking"]
        if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
            raise UserError(_("Only a warehouse manager or system administrator can validate inbound pickings."))
        if not self or self.filtered(lambda rec: rec.state != "done" or rec.is_replaced):
            raise UserError(_("Select only current completed blind stock counts."))
        picking_ids = picking_model.sudo().search([("blind_stock_count_id", "in", self.ids), ("is_blind_stock_count_receipt", "=", True), ("state", "not in", ["done", "cancel"])], order="id").ids
        pickings = picking_model.browse(picking_ids)
        if len(pickings) != len(self) or set(pickings.blind_stock_count_id.ids) != set(self.ids):
            raise UserError(_("Every selected blind stock count must have one unvalidated inbound picking before batch validation."))
        return pickings.action_queue_validate_blind_stock_count_pickings()

    def job_create_inbound_picking(self):
        count_line_model = self.env["blind.stock.count.line"]
        lot_model = self.env["stock.lot"]
        move_line_model = self.env["stock.move.line"]
        move_model = self.env["stock.move"]
        picking_model = self.env["stock.picking"]
        for rec in self:
            rec.with_context(blind_stock_count_receipt_queue_action=True).write({"receipt_generation_state": "running", "receipt_generation_error": False})
            try:
                with self.env.cr.savepoint():
                    if rec.state != "done" or rec.is_replaced:
                        raise UserError(_("Only the current completed blind stock count can generate an inbound picking."))
                    work_package = rec.work_package_id
                    if work_package.state not in ("in_progress", "done") or not work_package.receipt_picking_type_id or not work_package.receipt_source_location_id:
                        raise UserError(_("The work package is missing a valid inbound operation type or source location."))
                    if picking_model.sudo().search_count([("blind_stock_count_id", "=", rec.id), ("is_blind_stock_count_receipt", "=", True), ("state", "!=", "cancel")]):
                        raise UserError(_("An active inbound picking already exists for this blind stock count."))
                    clearance_pickings = picking_model.sudo().search([("blind_stock_count_work_package_id", "=", work_package.id), ("is_blind_stock_count_clearance", "=", True), ("state", "!=", "cancel")])
                    if not clearance_pickings or clearance_pickings.filtered(lambda picking: picking.state != "done"):
                        raise UserError(_("Complete every clearance outbound picking before generating an inbound picking."))
                    count_lines = count_line_model.sudo().search([("blind_stock_count_id", "=", rec.id)], order="blind_stock_count_pallet_id, product_id, id")
                    if not count_lines:
                        raise UserError(_("The blind stock count has no product lines."))
                    picking = picking_model.create({"picking_type_id": work_package.receipt_picking_type_id.id, "location_id": work_package.receipt_source_location_id.id, "location_dest_id": rec.location_id.id, "origin": rec.name, "partner_id": work_package.owner_id.id, "is_blind_stock_count_receipt": True, "blind_stock_count_work_package_id": work_package.id, "blind_stock_count_id": rec.id})
                    product_line_groups = {}
                    for line in count_lines:
                        product_line_groups.setdefault(line.product_id.id, []).append(line)
                    for lines in product_line_groups.values():
                        first_line = lines[0]
                        move = move_model.create({"name": first_line.product_id.display_name, "product_id": first_line.product_id.id, "product_uom_qty": sum(line.counted_qty for line in lines), "product_uom": first_line.product_id.uom_id.id, "picking_id": picking.id, "location_id": work_package.receipt_source_location_id.id, "location_dest_id": rec.location_id.id})
                        for line in lines:
                            lot = line.matched_lot_id
                            if line.product_tracking != "none" and not lot:
                                lot = lot_model.sudo().search([("product_id", "=", line.product_id.id), ("name", "=", line.lot_name)], limit=1)
                                if not lot:
                                    lot = lot_model.create({"name": line.lot_name, "product_id": line.product_id.id})
                            if line.product_tracking != "none" and not lot:
                                raise UserError(_("A lot or serial number is required for product %s.") % line.product_id.display_name)
                            move_line_model.create({"move_id": move.id, "picking_id": picking.id, "product_id": line.product_id.id, "product_uom_id": line.product_id.uom_id.id, "quantity": line.counted_qty, "location_id": work_package.receipt_source_location_id.id, "location_dest_id": rec.location_id.id, "lot_id": lot.id, "result_package_id": line.blind_stock_count_pallet_id.package_id.id, "owner_id": work_package.owner_id.id})
                    rec.with_context(blind_stock_count_receipt_queue_action=True).write({"receipt_generation_state": "done", "receipt_generation_error": False})
                    rec.message_post(body=_("Created inbound picking %s directly from blind stock count lines.") % picking.display_name)
            except Exception as error:
                rec.with_context(blind_stock_count_receipt_queue_action=True).write({"receipt_generation_state": "failed", "receipt_generation_error": str(error)})
                rec.message_post(body=_("Inbound picking generation failed: %s") % error)
        return True

    def action_return_to_counting(self):
        picking_model = self.env["stock.picking"]
        for rec in self:
            if picking_model.sudo().search_count([("blind_stock_count_id", "=", rec.id), ("is_blind_stock_count_receipt", "=", True), ("state", "!=", "cancel")]) or rec.receipt_generation_state in ("queued", "running"):
                raise UserError(_("Cancel the linked inbound picking or wait for its generation task before returning this blind stock count to counting."))
        return super().action_return_to_counting()

    def action_create_recount(self):
        picking_model = self.env["stock.picking"]
        for rec in self:
            if picking_model.sudo().search_count([("blind_stock_count_id", "=", rec.id), ("is_blind_stock_count_receipt", "=", True), ("state", "!=", "cancel")]) or rec.receipt_generation_state in ("queued", "running"):
                raise UserError(_("Cancel the linked inbound picking or wait for its generation task before creating a recount."))
        return super().action_create_recount()
