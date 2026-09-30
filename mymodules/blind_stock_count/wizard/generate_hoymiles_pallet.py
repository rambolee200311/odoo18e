# -*- coding: utf-8 -*-

import uuid

from odoo import _, fields, models
from odoo.exceptions import UserError


class BlindStockCountGenerateHoymilesPallet(models.TransientModel):
    _name = "blind.stock.count.generate.hoymiles.pallet"
    _description = "Generate Hoymiles Pallets"

    quantity = fields.Integer(string="Quantity", required=True)

    def action_generate_hoymiles_pallets(self):
        package_model = self.env["stock.quant.package"]
        sequence = self.env.ref("blind_stock_count.sequence_blind_stock_count_pallet")
        for rec in self:
            if rec.quantity <= 0:
                raise UserError(_("Quantity must be greater than zero."))
            barcodes = set()
            while len(barcodes) < rec.quantity:
                generated_barcodes = {uuid.uuid4().hex[:8].upper() for _ in range(rec.quantity - len(barcodes))}
                existing_barcodes = set(package_model.sudo().search([("barcode", "in", list(generated_barcodes))]).mapped("barcode"))
                barcodes.update(generated_barcodes - existing_barcodes)
            pallet_values = [{"name": sequence.next_by_id(), "barcode": barcode, "package_use": "disposable", "blind_stock_count_generation_type": "batch_generated"} for barcode in barcodes]
            package_model.create(pallet_values)
