# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class ReportOutboundLotCodeLabel(models.AbstractModel):
    _name = "report.stock_barcode_lite.report_outbound_lot_code_label"
    _description = "Outbound Lot Code Label Report"

    def _get_report_values(self, docids, data=None):
        order_model = self.env["world.depot.outbound.order"]
        docs = order_model.sudo().browse(docids).exists()
        sections_by_order = {}

        for rec in docs:
            whole_lines = rec.outbound_order_product_ids.filtered(lambda line: line.de_palletize == "N")
            partial_lines = rec.outbound_order_product_ids.filtered(lambda line: line.de_palletize != "N")

            if whole_lines and not rec.whole_pallet_picking_id:
                raise UserError(_("Please create the whole pallet picking before printing outbound lot labels."))

            if partial_lines and not rec.partial_pallet_picking_id:
                raise UserError(_("Please create the partial pallet picking before printing outbound lot labels."))

            sections = []
            if whole_lines:
                sections.append({
                    "title": _("Whole Pallet Picking"),
                    "picking": rec.whole_pallet_picking_id,
                    "lines": whole_lines,
                })
            if partial_lines:
                sections.append({
                    "title": _("Partial Pallet Picking"),
                    "picking": rec.partial_pallet_picking_id,
                    "lines": partial_lines,
                })

            sections_by_order[rec.id] = sections

        return {
            "doc_ids": docids,
            "doc_model": "world.depot.outbound.order",
            "docs": docs,
            "sections_by_order": sections_by_order,
        }