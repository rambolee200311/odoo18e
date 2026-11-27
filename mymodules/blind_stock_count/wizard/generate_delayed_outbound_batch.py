# -*- coding: utf-8 -*-

import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class BlindStockCountGenerateDelayedOutboundBatch(models.TransientModel):
    _name = "blind.stock.count.generate.delayed.outbound.batch"
    _description = "Generate Blind Stock Count Delayed Outbound Batch"

    work_package_id = fields.Many2one("blind.stock.count.work.package", string="Work Package", required=True, readonly=True)
    category_id = fields.Many2one(related="work_package_id.category_id", string="Product Category", readonly=True)
    date_from = fields.Date(string="Date From", required=True, default=fields.Date.today)
    date_to = fields.Date(string="Date To", required=True, default=fields.Date.today)

    @api.constrains("date_from", "date_to")
    def check_date_range(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("Date From must not be later than Date To."))

    def action_queue_generate_delayed_outbound_pickings(self):
        batch_model = self.env["blind.stock.count.delayed.outbound.batch"]
        for rec in self:
            if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
                raise UserError(_("Only a warehouse manager or system administrator can generate delayed outbound pickings."))
            if rec.work_package_id.state != "done":
                raise UserError(_("Delayed outbound pickings can only be generated from a completed work package."))
            if not rec.work_package_id.clearance_picking_type_id or rec.work_package_id.clearance_picking_type_id.code != "outgoing":
                raise UserError(_("Select an outgoing operation type on the work package before generating delayed outbound pickings."))
            if not rec.work_package_id.clearance_destination_location_id:
                raise UserError(_("Select an outbound destination location on the work package before generating delayed outbound pickings."))
            if batch_model.sudo().search_count([("work_package_id", "=", rec.work_package_id.id), ("state", "in", ["queued", "running"])]):
                raise UserError(_("A delayed outbound picking generation task is already queued or running for this work package."))
            if os.getenv("QUEUE_JOB__NO_DELAY") or self.env.context.get("queue_job__no_delay"):
                raise UserError(_("Queue workers must be enabled before submitting delayed outbound picking generation tasks."))
            batch = batch_model.create({"work_package_id": rec.work_package_id.id, "date_from": rec.date_from, "date_to": rec.date_to})
            job = batch.with_delay(description=_("Generate delayed outbound pickings for %s") % rec.work_package_id.display_name, identity_key="blind_stock_count_delayed_outbound:%s" % batch.id, channel="root.blind_stock_count").job_generate_delayed_outbound_pickings()
            queue_job = job.db_record() if job and hasattr(job, "db_record") else self.env["queue.job"]
            if queue_job:
                batch.write({"queue_job_id": queue_job.id})
            return {"type": "ir.actions.act_window", "name": _("Delayed Outbound Batch"), "res_model": "blind.stock.count.delayed.outbound.batch", "view_mode": "form", "res_id": batch.id, "target": "current"}
        return True
