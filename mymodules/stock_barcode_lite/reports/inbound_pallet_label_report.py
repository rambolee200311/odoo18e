# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class ReportInboundPalletLabel(models.AbstractModel):
    _name = "report.stock_barcode_lite.report_inbound_pallet_label"
    _description = "Inbound Pallet Label Report"

    def _get_report_values(self, docids, data=None):
        order_model = self.env["world.depot.inbound.order"]
        pallet_model = self.env["world.depot.inbound.order.product"]
        docids = docids or self.env.context.get("active_ids", [])
        docs = order_model.sudo().browse(docids).exists()
        pallets_by_order = {}

        for rec in docs:
            if rec.state != "confirm":
                raise UserError(
                    _('Only confirmed inbound orders can print "Inbound Pallet Labels".')
                )

        selected_pallet_ids = (data or {}).get("inbound_pallet_ids")
        if selected_pallet_ids:
            selected_pallets = pallet_model.sudo().search([("id", "in", selected_pallet_ids)])
            if set(selected_pallets.ids) != set(selected_pallet_ids):
                raise UserError(_("One or more selected pallets no longer exist."))

            for pallet in selected_pallets:
                if pallet.inbound_order_id.id not in docs.ids:
                    raise UserError(_("Selected pallets must belong to the printed inbound orders."))
                if pallet.is_reused_package:
                    raise UserError(_("Pallet \"%s\" reuses an existing package and cannot print an incomplete label.") % pallet.pallet_no)

            for rec in docs:
                pallets_by_order[rec.id] = selected_pallets.filtered(
                    lambda pallet: pallet.inbound_order_id.id == rec.id
                )
        else:
            for rec in docs:
                pallets_by_order[rec.id] = rec.inbound_order_product_ids

        return {
            "doc_ids": docs.ids,
            "doc_model": "world.depot.inbound.order",
            "docs": docs,
            "pallets_by_order": pallets_by_order,
        }


class ReportInboundPickingProducts(models.AbstractModel):
    _name = "report.stock_barcode_lite.report_inbound_picking_products"
    _description = "Inbound Picking Products Report"

    def _get_report_values(self, docids, data=None):
        order_model = self.env["world.depot.inbound.order"]
        docs = order_model.sudo().browse(docids).exists()

        for rec in docs:
            if not rec.stock_picking_id:
                raise UserError(
                    _('Please create the inbound picking before printing "Inbound Picking Products".')
                )

        return {
            "doc_ids": docids,
            "doc_model": "world.depot.inbound.order",
            "docs": docs,
        }
