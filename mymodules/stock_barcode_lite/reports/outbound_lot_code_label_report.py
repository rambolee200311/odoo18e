# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class ReportOutboundLotCodeLabel(models.AbstractModel):
    _name = "report.stock_barcode_lite.report_outbound_lot_code_label"
    _description = "Outbound Lot Code Label Report"

    def _get_report_values(self, docids, data=None):
        order_model = self.env["world.depot.outbound.order"]
        line_model = self.env["world.depot.outbound.order.product"]
        docs = order_model.sudo().browse(docids).exists()
        sections_by_order = {}

        for rec in docs:
            if not (rec.whole_pallet_picking_id or rec.partial_pallet_picking_id):
                raise UserError(_("Please create an outbound picking before printing outbound lot labels."))
            sections = []
            for root_picking, title in (
                (rec.whole_pallet_picking_id, _("Whole Pallet Picking")),
                (rec.partial_pallet_picking_id, _("Partial Pallet Picking")),
            ):
                if not root_picking:
                    continue
                picking_list = rec.get_sunrise_picking_backorder_chain(root_picking).filtered(
                    lambda picking: picking.state != "cancel"
                ).sorted("id")
                for picking in picking_list:
                    move_lines = picking.move_line_ids.filtered(
                        lambda move_line: move_line.state != "cancel" and move_line.quantity > 0
                    )
                    missing_detail_move_line = move_lines.filtered(
                        lambda move_line: not move_line.move_id.outbound_order_product_id
                    )[:1]
                    if missing_detail_move_line:
                        raise UserError(_("Outbound picking %(picking)s move line %(move_line)s has no outbound product detail.") % {
                            "picking": picking.name,
                            "move_line": missing_detail_move_line.id,
                        })
                    missing_package_move_line = move_lines.filtered(
                        lambda move_line: not move_line.package_id
                    )[:1]
                    if missing_package_move_line:
                        raise UserError(_("Outbound picking %(picking)s move line %(move_line)s has no pallet.") % {
                            "picking": picking.name,
                            "move_line": missing_package_move_line.id,
                        })
                    line_ids = move_lines.mapped("move_id.outbound_order_product_id")
                    lines_by_id = {
                        line.id: line
                        for line in line_model.sudo().browse(line_ids).exists().filtered(lambda line: line.outbound_order_id == rec)
                    }
                    unmatched_detail_move_line = move_lines.filtered(
                        lambda move_line: move_line.move_id.outbound_order_product_id not in lines_by_id
                    )[:1]
                    if unmatched_detail_move_line:
                        raise UserError(_("Outbound picking %(picking)s move line %(move_line)s is not linked to this outbound order.") % {
                            "picking": picking.name,
                            "move_line": unmatched_detail_move_line.id,
                        })
                    pallet_group_map = {}
                    for move_line in move_lines:
                        line = lines_by_id[move_line.move_id.outbound_order_product_id]
                        package = move_line.package_id
                        pallet_group = pallet_group_map.setdefault(package.id, {
                            "pallet_no": line.pallet_no or package.name or "",
                            "actual_package_name": package.name or "",
                            "has_package_mismatch": False,
                            "rows": [],
                            "row_map": {},
                        })
                        if line.package_id.id != package.id:
                            pallet_group["has_package_mismatch"] = True
                        row_key = (line.id, move_line.product_id.id, move_line.lot_id.id, move_line.lot_name or "")
                        row = pallet_group["row_map"].get(row_key)
                        if not row:
                            row = {
                                "product_name": move_line.product_id.display_name,
                                "lot_name": move_line.lot_id.name or move_line.lot_name or line.lot_name or "",
                                "barcode": move_line.product_id.barcode or "",
                                "box_in_qty": line.box_in_qty or "",
                                "uom_name": line.u8_aux_uom_name or "",
                                "quantity": 0.0,
                                "unit": line.castunitid or "",
                            }
                            pallet_group["row_map"][row_key] = row
                            pallet_group["rows"].append(row)
                        row["quantity"] += move_line.quantity
                    pallet_groups = list(pallet_group_map.values())
                    for pallet_group in pallet_groups:
                        pallet_group.pop("row_map")
                    if not pallet_groups:
                        continue
                    sections.append({
                        "title": title,
                        "picking": picking,
                        "pallet_groups": pallet_groups,
                    })

            if not sections:
                raise UserError(_("The outbound picking has no pallet move lines linked to outbound product details."))

            sections_by_order[rec.id] = sections

        return {
            "doc_ids": docids,
            "doc_model": "world.depot.outbound.order",
            "docs": docs,
            "sections_by_order": sections_by_order,
        }
