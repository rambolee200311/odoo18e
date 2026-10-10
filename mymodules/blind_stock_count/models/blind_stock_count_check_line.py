# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class BlindStockCountCheckLine(models.Model):
    _name = "blind.stock.count.check.line"
    _description = "Blind Stock Count Check Line"
    _order = "id desc"
    _sql_constraints = [("blind_stock_count_check_source_line_unique", "unique(blind_stock_count_check_id, source_line_id)", "A source line can only be sampled once on the same blind stock count check.")]

    blind_stock_count_check_id = fields.Many2one("blind.stock.count.check", string="Blind Stock Count Check", required=True, ondelete="cascade", copy=False, index=True)
    source_line_id = fields.Many2one("blind.stock.count.line", string="Source Line", ondelete="restrict", copy=False, index=True)
    blind_stock_count_id = fields.Many2one(related="blind_stock_count_check_id.blind_stock_count_id", string="Blind Stock Count", readonly=True, store=True, index=True)
    source_pallet_id = fields.Many2one(related="source_line_id.blind_stock_count_pallet_id", string="Source Pallet", readonly=True, store=True, index=True)
    package_id = fields.Many2one(related="source_pallet_id.package_id", string="Pallet Number", readonly=True, store=True, index=True)
    product_id = fields.Many2one(related="source_line_id.product_id", string="Product", readonly=True, store=True, index=True)
    product_tracking = fields.Selection(related="source_line_id.product_tracking", string="Tracking", readonly=True, store=True, index=True)
    lot_name = fields.Char(related="source_line_id.lot_name", string="Lot / Serial Number", readonly=True, store=True, index=True)
    source_counted_qty = fields.Float(related="source_line_id.counted_qty", string="Source Counted Quantity", readonly=True)
    checked_qty = fields.Float(string="Checked Quantity", required=True, default=1.0, copy=False)
    anomaly_status = fields.Selection([("out_of_scope", "Out of Scope"), ("not_in_blind", "Not in Blind Count"), ("not_matched", "Not Matched")], string="Anomaly Status", copy=False, index=True)
    match_status = fields.Selection([("matched", "Matched"), ("not_matched", "Not Matched"), ("out_of_scope", "Out of Scope"), ("not_in_blind", "Not in Blind Count")], string="Match Status", compute="compute_match_status", store=True, readonly=True, index=True)
    is_matched = fields.Boolean(string="Matched", compute="compute_is_matched", store=True, readonly=True)
    scanned_pallet_code = fields.Char(string="Scanned Pallet Code", copy=False, index=True)
    scanned_product_id = fields.Many2one("product.product", string="Scanned Product", copy=False, index=True)
    scanned_product_barcode = fields.Char(string="Scanned Product Barcode", copy=False, index=True)
    scanned_lot_name = fields.Char(string="Scanned Lot / Serial Number", copy=False, index=True)
    checked_by_id = fields.Many2one("res.users", string="Checked By", required=True, default=lambda self: self.env.user.id, readonly=True, copy=False, index=True)
    checked_at = fields.Datetime(string="Checked At", required=True, default=fields.Datetime.now, readonly=True, copy=False, index=True)
    note = fields.Char(string="Notes", copy=False)

    @api.depends("anomaly_status", "source_line_id", "checked_qty", "source_counted_qty", "product_id.uom_id.rounding")
    def compute_match_status(self):
        for rec in self:
            if rec.anomaly_status:
                rec.match_status = rec.anomaly_status
            elif rec.source_line_id:
                rec.match_status = "matched" if float_compare(rec.checked_qty, rec.source_counted_qty, precision_rounding=rec.product_id.uom_id.rounding) == 0 else "not_matched"
            else:
                rec.match_status = "not_in_blind"

    @api.depends("match_status")
    def compute_is_matched(self):
        for rec in self:
            rec.is_matched = rec.match_status == "matched"

    @api.model_create_multi
    def create(self, vals_list):
        check_model = self.env["blind.stock.count.check"]
        source_line_model = self.env["blind.stock.count.line"]
        for vals in vals_list:
            check = check_model.sudo().search([("id", "=", vals.get("blind_stock_count_check_id")), ("state", "=", "checking")], limit=1)
            source_line = source_line_model.sudo().search([("id", "=", vals.get("source_line_id")), ("blind_stock_count_id", "=", check.blind_stock_count_id.id)], limit=1) if check else False
            if not check or (not source_line and not vals.get("anomaly_status")):
                raise UserError(_("An active blind stock count check and a source line or anomaly status are required."))
            if source_line.product_tracking == "serial" and vals.get("checked_qty", 1.0) != 1.0:
                raise UserError(_("A serial-numbered product must have a checked quantity of 1."))
        return super().create(vals_list)

    @api.constrains("checked_qty")
    def check_checked_qty(self):
        for rec in self:
            if rec.source_line_id and rec.checked_qty <= 0:
                raise ValidationError(_("The checked quantity must be greater than zero."))
            if not rec.source_line_id and rec.checked_qty < 0:
                raise ValidationError(_("The checked quantity cannot be negative."))
            if rec.product_tracking == "serial" and rec.checked_qty != 1:
                raise ValidationError(_("A serial-numbered product must have a checked quantity of 1."))

    def write(self, vals):
        if {"blind_stock_count_check_id", "source_line_id"}.intersection(vals):
            raise UserError(_("Delete and add the sampled line again to change its source."))
        for rec in self:
            if rec.blind_stock_count_check_id.state != "checking":
                raise UserError(_("Sampled lines can only be changed while the blind stock count check is active."))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.blind_stock_count_check_id.state != "checking":
                raise UserError(_("Sampled lines can only be deleted while the blind stock count check is active."))
        return super().unlink()
