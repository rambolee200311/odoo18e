# -*- coding: utf-8 -*-

import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class BlindStockCountGenerateClearanceBatch(models.TransientModel):
    _name = "blind.stock.count.generate.clearance.batch"
    _description = "Generate Blind Stock Count Clearance Batch"

    work_package_id = fields.Many2one("blind.stock.count.work.package", string="Work Package", required=True, readonly=True)
    maximum_lines_per_clearance = fields.Integer(string="Maximum Lines per Clearance", required=True, default=300)

    @api.constrains("maximum_lines_per_clearance")
    def check_maximum_lines_per_clearance(self):
        for rec in self:
            if rec.maximum_lines_per_clearance <= 0:
                raise ValidationError(_("Maximum lines per clearance must be greater than zero."))

    def action_generate_clearance_batch(self):
        clearance_batch_model = self.env["blind.stock.count.clearance.batch"]
        picking_model = self.env["stock.picking"]
        for rec in self:
            if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
                raise UserError(_("Only a warehouse manager or system administrator can generate a clearance order."))
            if rec.work_package_id.state != "done":
                raise UserError(_("A clearance order can only be generated from a completed work package."))
            if clearance_batch_model.sudo().search_count([("work_package_id", "=", rec.work_package_id.id), ("state", "in", ["queued", "running"])]):
                raise UserError(_("A clearance picking generation task is already queued or running for this work package."))
            if picking_model.sudo().search_count([("blind_stock_count_work_package_id", "=", rec.work_package_id.id), ("is_blind_stock_count_clearance", "=", True), ("state", "!=", "cancel")]):
                raise UserError(_("An active clearance outbound picking already exists for this work package."))
            if os.getenv("QUEUE_JOB__NO_DELAY") or self.env.context.get("queue_job__no_delay"):
                raise UserError(_("Queue workers must be enabled before submitting clearance generation tasks."))
            batch = clearance_batch_model.create({"work_package_id": rec.work_package_id.id, "maximum_lines_per_clearance": rec.maximum_lines_per_clearance, "source_quant_count": 0, "normalized_negative_quant_count": 0})
            job = batch.with_delay(description=_("Generate clearance outbound pickings for %s") % rec.work_package_id.display_name, identity_key="blind_stock_count_clearance:%s" % batch.id, channel="root.blind_stock_count").job_generate_outbound_pickings()
            queue_job = job.db_record() if job and hasattr(job, "db_record") else self.env["queue.job"]
            if queue_job:
                batch.write({"queue_job_id": queue_job.id})
            return {"type": "ir.actions.act_window", "name": _("Clearance Batch"), "res_model": "blind.stock.count.clearance.batch", "view_mode": "form", "res_id": batch.id, "target": "current"}
        return True
