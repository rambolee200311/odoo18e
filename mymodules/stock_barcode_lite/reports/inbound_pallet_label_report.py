# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class ReportInboundPalletLabel(models.AbstractModel):
    _name = "report.stock_barcode_lite.report_inbound_pallet_label"
    _description = "Inbound Pallet Label Report"

    def _get_report_values(self, docids, data=None):
        order_model = self.env["world.depot.inbound.order"]
        docs = order_model.sudo().browse(docids).exists()

        for rec in docs:
            # The label QR code includes the receipt picking, so the receipt must exist before printing.
            if not rec.stock_picking_id:
                raise UserError(
                    _('Please create the inbound picking before printing "Inbound Pallet Labels".')
                )

        return {
            "doc_ids": docids,
            "doc_model": "world.depot.inbound.order",
            "docs": docs,
        }