# -*- coding: utf-8 -*-

from odoo import models


class ReportSystemPalletLabel(models.AbstractModel):
    _name = "report.stock_barcode_lite.report_system_pallet_label"
    _description = "System Pallet Label Report"

    def _get_report_values(self, docids, data=None):
        package_model = self.env["stock.quant.package"]
        move_line_model = self.env["stock.move.line"]
        package_ids = package_model.sudo().browse(docids or self.env.context.get("active_ids", [])).exists()
        product_lines_by_package = {package.id: {} for package in package_ids}
        move_line_ids = move_line_model.sudo().search([
            ("result_package_id", "in", package_ids.ids),
            ("picking_id", "in", package_ids.mapped("inbound_order_id.stock_picking_id").ids),
            ("quantity", ">", 0),
        ], order="id asc")

        for move_line in move_line_ids:
            package_lines = product_lines_by_package.get(move_line.result_package_id.id)
            if package_lines is None:
                continue
            product_line = package_lines.setdefault(move_line.product_id.id, {
                "source_line": move_line,
                "quantity": 0.0,
            })
            product_line["quantity"] += move_line.quantity

        for package in package_ids:
            if product_lines_by_package[package.id]:
                continue
            pallet_lines = package.inbound_order_id.inbound_order_product_ids.filtered(
                lambda pallet: pallet.package_id == package
            )
            for pallet in pallet_lines:
                for product_detail in pallet.inbound_order_product_pallet_ids:
                    product_line = product_lines_by_package[package.id].setdefault(product_detail.product_id.id, {
                        "source_line": product_detail,
                        "quantity": 0.0,
                    })
                    product_line["quantity"] += product_detail.quantity

        return {
            "doc_ids": package_ids.ids,
            "doc_model": "stock.quant.package",
            "docs": package_ids,
            "product_lines_by_package": {
                package_id: list(product_lines.values())
                for package_id, product_lines in product_lines_by_package.items()
            },
        }
