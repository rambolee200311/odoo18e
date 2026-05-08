# -*- coding: utf-8 -*-

from odoo import api, models

from .utils import (
    portal_format_date,
    portal_owner_domain,
    portal_package_container_from_name,
    portal_package_shipping_map,
    portal_product_code,
)


class OutboundOrderSNDetail(models.Model):
    _inherit = "world.depot.outbound.order.sn.detail"

    def init(self):
        return True

    @api.model
    def search_sn(self, sn_code):
        if not sn_code:
            return {"status": "NOT_FOUND", "data": {}}
        detail_env = self.env["world.depot.outbound.order.sn.detail"].sudo()
        detail_domain = [("lot_name", "=", sn_code)] + portal_owner_domain(self.env, "project.owner")
        detail = detail_env.search(detail_domain, limit=1, order="p_date desc, id desc")
        if detail:
            return {"status": "FOUND", "data": self.get_sn_result_from_detail(detail)}
        move_line = self.get_sn_move_line(sn_code)
        if not move_line:
            return {"status": "NOT_FOUND", "data": {}}
        order = self.get_sn_outbound_order(move_line)
        if not order:
            return {"status": "NOT_FOUND", "data": {}}
        return {"status": "FOUND", "data": self.get_sn_result_from_move_line(move_line, order)}

    @api.model
    def get_sn_move_line(self, sn_code):
        move_line_env = self.env["stock.move.line"].sudo()
        domain = [("lot_id.name", "=", sn_code), ("product_id", "!=", False)] + portal_owner_domain(self.env, "owner_id")
        return move_line_env.search(domain, limit=1, order="date desc, id desc")

    @api.model
    def get_sn_outbound_order(self, move_line):
        picking = move_line.picking_id
        if not picking:
            return self.env["world.depot.outbound.order"].sudo()
        domain = ["|", ("picking_PICK", "=", picking.id), ("picking_Out", "=", picking.id)] + portal_owner_domain(self.env, "project.owner")
        return self.env["world.depot.outbound.order"].sudo().search(domain, limit=1)

    @api.model
    def get_sn_result_from_detail(self, detail):
        order = detail.order_id
        lot = detail.lot_id
        product = detail.product_id
        return {
            "sn_code": detail.lot_name or "",
            "product_code": portal_product_code(product),
            "product_name": product.display_name or detail.product_name or "",
            "outbound_no": order.billno or order.reference or detail.reference or "",
            "outbound_date": portal_format_date(order.o_date or detail.p_date),
            "container_no": lot.cntrno or "",
            "bl_no": lot.bill_of_lading or "",
            "state": order.status or order.state or "",
        }

    @api.model
    def get_sn_result_from_move_line(self, move_line, order):
        package = move_line.package_id or move_line.result_package_id
        info_by_package = portal_package_shipping_map(self.env, [package.id] if package else [])
        info = info_by_package.get(package.id, {}) if package else {}
        lot = move_line.lot_id
        product = move_line.product_id
        return {
            "sn_code": lot.name or "",
            "product_code": portal_product_code(product),
            "product_name": product.display_name or product.name or "",
            "outbound_no": order.billno or order.reference or "",
            "outbound_date": portal_format_date(order.o_date or move_line.picking_id.date_done or move_line.date),
            "container_no": lot.cntrno or info.get("container_no") or portal_package_container_from_name(package.name if package else ""),
            "bl_no": lot.bill_of_lading or info.get("bl_no") or "",
            "state": order.status or order.state or "",
        }
