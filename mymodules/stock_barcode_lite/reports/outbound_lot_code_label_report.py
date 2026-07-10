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
            whole_pallet_groups = []
            partial_pallet_groups = []

            if whole_lines and not rec.whole_pallet_picking_id:
                raise UserError(_("Please create the whole pallet picking before printing outbound lot labels."))

            if partial_lines and not rec.partial_pallet_picking_id:
                raise UserError(_("Please create the partial pallet picking before printing outbound lot labels."))

            for pallet_no in list(dict.fromkeys(whole_lines.mapped("pallet_no"))):
                whole_pallet_groups.append({
                    "pallet_no": pallet_no,
                    "lines": whole_lines.filtered(lambda line: line.pallet_no == pallet_no),
                })

            for pallet_no in list(dict.fromkeys(partial_lines.mapped("pallet_no"))):
                partial_pallet_groups.append({
                    "pallet_no": pallet_no,
                    "lines": partial_lines.filtered(lambda line: line.pallet_no == pallet_no),
                })

            sections = []
            if whole_lines:
                sections.append({
                    "title": _("Whole Pallet Picking"),
                    "picking": rec.whole_pallet_picking_id,
                    "pallet_groups": whole_pallet_groups,
                })
            if partial_lines:
                sections.append({
                    "title": _("Partial Pallet Picking"),
                    "picking": rec.partial_pallet_picking_id,
                    "pallet_groups": partial_pallet_groups,
                })

            sections_by_order[rec.id] = sections

        return {
            "doc_ids": docids,
            "doc_model": "world.depot.outbound.order",
            "docs": docs,
            "sections_by_order": sections_by_order,
        }