# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class ReportInboundLotCodeLabel(models.AbstractModel):
    _name = "report.stock_barcode_lite.report_inbound_lot_code_label"
    _description = "Inbound Lot Code Label Report"

    def _get_report_values(self, docids, data=None):
        order_model = self.env["world.depot.inbound.order"]
        docs = order_model.sudo().browse(docids).exists()
        lines_by_order = {}

        for rec in docs:
            if rec.state != "confirm":
                raise UserError(
                    _('Only confirmed inbound orders can print "Inbound Product Lot Code Labels".')
                )

            lines_by_order[rec.id] = rec.inbound_order_product_ids.mapped("inbound_order_product_pallet_ids")

        return {
            "doc_ids": docids,
            "doc_model": "world.depot.inbound.order",
            "docs": docs,
            "lines_by_order": lines_by_order,
        }