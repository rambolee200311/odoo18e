# -*- coding: utf-8 -*-

import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class OutboundProductImportWizard(models.TransientModel):
    _name = "outbound.product.import.wizard"
    _description = "Outbound Product Import Wizard"
    _order = "id desc"

    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", required=True, readonly=True, index=True, copy=False)
    reference = fields.Char(string="Reference", copy=False, readonly=True)
    file = fields.Binary(string="Excel File", required=True, copy=False)
    filename = fields.Char(string="Filename", copy=False)

    def action_import_excel(self):
        for rec in self:
            outbound_order = rec.outbound_order_id
            if outbound_order.state != "new":
                raise UserError(_("Only new outbound orders can import products."))
            if outbound_order.outbound_order_product_ids:
                raise UserError(_("This outbound order already has pallet/product lines."))
            if not rec.file:
                raise UserError(_("Please upload an Excel file."))

            import_record = rec.env["stock.barcode.lite.sunrise.order.import"].create({
                "name": _("Sunrise Outbound Import - %s") % (outbound_order.billno or outbound_order.reference or outbound_order.id),
                "import_type": "outbound",
                "outbound_order_id": outbound_order.id,
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
