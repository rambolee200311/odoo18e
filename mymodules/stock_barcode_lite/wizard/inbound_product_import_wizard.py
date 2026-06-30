# -*- coding: utf-8 -*-

import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class InboundProductImportWizard(models.TransientModel):
    _name = "inbound.product.import.wizard"
    _description = "Chenyang Chemical Inbound Product Import Wizard"
    _order = "id desc"

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", required=True, readonly=True, index=True, copy=False)
    file = fields.Binary(string="Excel File", required=True, copy=False)
    filename = fields.Char(string="Filename", copy=False)

    def action_import_excel(self):
        for rec in self:
            inbound_order = rec.inbound_order_id
            if inbound_order.state != "new":
                raise UserError(_("Only new inbound orders can import products."))
            if inbound_order.inbound_order_product_ids:
                raise UserError(_("This inbound order already has pallet/product lines."))
            if not rec.file:
                raise UserError(_("Please upload an Excel file."))

            import_record = rec.env["stock.barcode.lite.sunrise.order.import"].create({
                "name": _("Sunrise Inbound Import - %s") % (inbound_order.billno or inbound_order.reference or inbound_order.id),
                "import_type": "inbound",
                "inbound_order_id": inbound_order.id,
                "filename": rec.filename,
            })
            import_record.process_import(base64.b64decode(rec.file), rec.filename)
            return {
                "type": "ir.actions.act_window",
                "name": _("Sunrise Order Import"),
                "res_model": "stock.barcode.lite.sunrise.order.import",
                "view_mode": "form",
                "views": [(False, "form")],
                "res_id": import_record.id,
                "target": "current",
            }
        return {"type": "ir.actions.act_window_close"}
