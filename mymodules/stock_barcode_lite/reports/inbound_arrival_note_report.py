# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class ReportInboundArrivalNote(models.AbstractModel):
    _name = "report.stock_barcode_lite.report_inbound_arrival_note"
    _description = "Inbound Arrival Note Report"

    def _get_report_values(self, docids, data=None):
        order_model = self.env["world.depot.inbound.order"]
        docs = order_model.sudo().browse(docids).exists()
        summary_by_order = {}
        for rec in docs:
            if rec.state != "confirm":
                raise UserError(_("Only confirmed inbound orders can print \"Inbound Arrival Note\"."))
            pallet_lines = rec.inbound_order_product_ids
            summary_by_order[rec.id] = {
                "pallet_total": sum(pallet_lines.mapped("pallets")),
                "product_total": len(pallet_lines.mapped("inbound_order_product_pallet_ids")),
            }
        return {
            "doc_ids": docs.ids,
            "doc_model": "world.depot.inbound.order",
            "docs": docs,
            "summary_by_order": summary_by_order,
        }
