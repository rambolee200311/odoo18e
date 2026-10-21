# -*- coding: utf-8 -*-

from odoo import fields, models


class BlindStockCountCancelledPickingLog(models.Model):
    _name = "blind.stock.count.cancelled.picking.log"
    _description = "Blind Stock Count Cancelled Picking Log"
    _order = "id desc"
    _sql_constraints = [("blind_stock_count_cancelled_picking_log_unique", "unique(work_package_id, picking_id)", "A picking can only be logged once for the same work package.")]

    work_package_id = fields.Many2one("blind.stock.count.work.package", string="Work Package", required=True, ondelete="cascade", copy=False, index=True)
    picking_id = fields.Many2one("stock.picking", string="Picking", required=True, ondelete="restrict", copy=False, index=True)
    picking_name = fields.Char(string="Picking Number", required=True, readonly=True, copy=False, index=True)
    state_before = fields.Char(string="State Before Cancellation", required=True, readonly=True, copy=False)
    picking_type_id = fields.Many2one("stock.picking.type", string="Operation Type", readonly=True, copy=False, index=True)
    source_location_id = fields.Many2one("stock.location", string="Source Location", readonly=True, copy=False, index=True)
    destination_location_id = fields.Many2one("stock.location", string="Destination Location", readonly=True, copy=False, index=True)
    cancelled_by_id = fields.Many2one("res.users", string="Cancelled By", required=True, readonly=True, copy=False, index=True)
    cancelled_at = fields.Datetime(string="Cancelled At", required=True, readonly=True, copy=False, index=True)
    reason = fields.Char(string="Reason", required=True, readonly=True, copy=False)
