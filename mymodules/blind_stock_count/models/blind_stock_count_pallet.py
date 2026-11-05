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

    @api.constrains("blind_stock_count_id", "package_id")
    def check_package_available_for_blind_stock_count(self):
        pallet_model = self.env["blind.stock.count.pallet"]
        quant_model = self.env["stock.quant"]
        move_line_model = self.env["stock.move.line"]
        for rec in self:
            if not rec.blind_stock_count_id or not rec.package_id:
                continue
            used_pallet = pallet_model.sudo().search([("package_id", "=", rec.package_id.id), ("blind_stock_count_id", "!=", rec.blind_stock_count_id.id), ("blind_stock_count_id.state", "!=", "cancel")], limit=1)
            if used_pallet:
                raise UserError(_("Pallet %s is already recorded on blind stock count %s.") % (rec.package_id.display_name, used_pallet.blind_stock_count_id.display_name))
            stock_quant = quant_model.sudo().search([("package_id", "=", rec.package_id.id), ("quantity", ">", 0)], limit=1)
            if stock_quant:
                raise UserError(_("Pallet %s already has stock in %s.") % (rec.package_id.display_name, stock_quant.location_id.display_name))
            inbound_move_line = move_line_model.sudo().search([("result_package_id", "=", rec.package_id.id), ("picking_id.picking_type_id.code", "=", "incoming"), ("picking_id.state", "!=", "cancel")], limit=1)
            if inbound_move_line:
                raise UserError(_("Pallet %s was already used by inbound picking %s.") % (rec.package_id.display_name, inbound_move_line.picking_id.display_name))

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
