# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BlindStockCountPallet(models.Model):
    _name = "blind.stock.count.pallet"
    _description = "Blind Stock Count Pallet"
    _order = "id desc"
    _sql_constraints = [("blind_stock_count_package_unique", "unique(blind_stock_count_id, package_id)", "The pallet can only be recorded once on the same blind stock count.")]

    blind_stock_count_id = fields.Many2one("blind.stock.count", string="Blind Stock Count", required=True, ondelete="cascade", copy=False, index=True)
    location_id = fields.Many2one(related="blind_stock_count_id.location_id", string="Count Location", readonly=True, store=True, index=True)
    state = fields.Selection(related="blind_stock_count_id.state", string="Status", readonly=True, store=True, index=True)
    package_id = fields.Many2one("stock.quant.package", string="Pallet Number", required=True, copy=False, index=True)
    product_lines = fields.One2many("blind.stock.count.line", "blind_stock_count_pallet_id", string="Product Lines", copy=False)

    def get_scan_data(self):
        line_model = self.env["blind.stock.count.line"]
        result = []
        for rec in self:
            product_lines = line_model.sudo().search([("blind_stock_count_pallet_id", "=", rec.id)], order="id desc")
            product_summaries = {}
            for line in product_lines:
                product_summary = product_summaries.setdefault(line.product_id.id, {"id": line.product_id.id, "name": line.product_id.display_name, "counted_qty": 0.0})
                product_summary["counted_qty"] += line.counted_qty
            result.append({"id": rec.id, "name": rec.package_id.name, "barcode": rec.package_id.barcode or "", "line_count": len(product_lines), "product_summaries": list(product_summaries.values()), "product_lines": [{"id": line.id, "product_id": line.product_id.id, "name": line.product_id.display_name, "barcode": line.product_barcode or "", "tracking": line.product_tracking, "lot_name": line.lot_name or "", "counted_qty": line.counted_qty} for line in product_lines]})
        return result[0] if len(result) == 1 else result

    @api.model_create_multi
    def create(self, vals_list):
        count_model = self.env["blind.stock.count"]
        for vals in vals_list:
            count = count_model.sudo().search([("id", "=", vals.get("blind_stock_count_id")), ("state", "=", "counting")], limit=1)
            if not count:
                raise UserError(_("Pallets can only be added to an active blind stock count."))
        return super().create(vals_list)

    def write(self, vals):
        for rec in self:
            if rec.state != "counting":
                raise UserError(_("Pallets can only be changed while blind stock counting is active."))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state != "counting":
                raise UserError(_("Pallets can only be deleted while blind stock counting is active."))
        return super().unlink()
