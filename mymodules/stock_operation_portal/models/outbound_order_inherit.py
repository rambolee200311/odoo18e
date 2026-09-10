# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models

from .utils import portal_attachment_row, portal_binary_field_row, portal_detect_attachment_type, portal_doc_binary_row, portal_format_datetime, portal_package_container_from_name, portal_package_shipping_map, portal_product_code, portal_product_name, portal_project_domain


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    stock_operation_portal_confirmed = fields.Boolean(string="Portal Confirmed", readonly=True, copy=False, index=True, tracking=True)
    stock_operation_portal_confirm_user_id = fields.Many2one("res.users", string="Portal Confirmed By", readonly=True, copy=False, tracking=True)
    stock_operation_portal_confirm_time = fields.Datetime(string="Portal Confirmed At", readonly=True, copy=False, tracking=True)

    @api.model
    def get_outbound_detail(self, outbound_id):
        order = self.get_outbound_order(outbound_id)
        if not order:
            return []
        rows = self.get_outbound_detail_from_move_lines(order)
        if rows:
            return rows
        detail_env = self.env["world.depot.outbound.order.sn.detail"].sudo()
        details = detail_env.search([("order_id", "=", order.id)], order="p_date desc, id desc")
        rows = []
        for detail in details:
            product = detail.product_id
            lot = detail.lot_id
            rows.append({
                "outbound_no": order.billno or order.reference or "",
                "reference": order.reference or "",
                "bl_no": lot.bill_of_lading or "",
                "container_no": lot.cntrno or "",
                "package_name": "",
                "product_code": portal_product_code(product),
                "product_name": portal_product_name(product) or detail.product_name or "",
                "quantity": 1,
                "sn_code": detail.lot_name or "",
                "scan_time": portal_format_datetime(detail.p_date),
            })
        return rows

    @api.model
    def get_outbound_attachments(self, outbound_id):
        order = self.get_outbound_order(outbound_id)
        if not order:
            return []
        doc_env = self.env["world.depot.outbound.order.docs"].sudo()
        attachment_env = self.env["ir.attachment"].sudo()
        docs = doc_env.search([("outbound_order_id", "=", order.id)], order="id desc")
        doc_by_filename = {doc.filename: doc for doc in docs if doc.filename}
        attachments = attachment_env.search([("res_model", "=", "world.depot.outbound.order"), ("res_id", "=", order.id), ("res_field", "=", False)], order="id desc")
        rows = []
        seen_names = set()
        for attachment in attachments:
            datas_fname = attachment.datas_fname if "datas_fname" in attachment._fields else ""
            file_name = attachment.name or datas_fname or ""
            doc = doc_by_filename.get(file_name)
            file_type = portal_detect_attachment_type(file_name, doc.doc_type) if doc else portal_detect_attachment_type(file_name)
            rows.append(portal_attachment_row(attachment, file_type))
            seen_names.add(file_name)
        pod_row = portal_binary_field_row(order, "pod_file", "pod_filename", "POD")
        if pod_row and pod_row["file_name"] not in seen_names:
            rows.append(pod_row)
            seen_names.add(pod_row["file_name"])
        for doc in docs:
            if doc.filename and doc.file and doc.filename not in seen_names:
                rows.append(portal_doc_binary_row(doc, portal_detect_attachment_type(doc.filename, doc.doc_type)))
                seen_names.add(doc.filename)
        return rows

    @api.model
    def get_outbound_order(self, outbound_id):
        if not outbound_id:
            return self.env["world.depot.outbound.order"].sudo()
        domain = [("id", "=", outbound_id)] + portal_project_domain(self.env, "project")
        return self.env["world.depot.outbound.order"].sudo().search(domain, limit=1)

    @api.model
    def get_outbound_shipping_map(self, orders):
        result = defaultdict(lambda: {"containers": set(), "bls": set()})
        picking_to_order = {}
        for order in orders:
            if order.picking_PICK:
                picking_to_order[order.picking_PICK.id] = order.id
            if order.picking_Out:
                picking_to_order[order.picking_Out.id] = order.id
        if not picking_to_order:
            return result
        move_line_env = self.env["stock.move.line"].sudo()
        move_lines = move_line_env.search([("picking_id", "in", list(picking_to_order)), ("product_id", "!=", False)])
        package_ids = set(move_lines.mapped("package_id").ids + move_lines.mapped("result_package_id").ids)
        info_by_package = portal_package_shipping_map(self.env, list(package_ids))
        for move_line in move_lines:
            order_id = picking_to_order.get(move_line.picking_id.id)
            if not order_id:
                continue
            package = move_line.package_id or move_line.result_package_id
            info = info_by_package.get(package.id, {}) if package else {}
            container_no = move_line.lot_id.cntrno or info.get("container_no") or portal_package_container_from_name(package.name if package else "")
            bl_no = move_line.lot_id.bill_of_lading or info.get("bl_no") or ""
            if container_no:
                result[order_id]["containers"].add(container_no)
            if bl_no:
                result[order_id]["bls"].add(bl_no)
        return result

    @api.model
    def get_outbound_detail_from_move_lines(self, order):
        picking_ids = []
        if order.picking_PICK:
            picking_ids.append(order.picking_PICK.id)
        if order.picking_Out:
            picking_ids.append(order.picking_Out.id)
        if not picking_ids:
            return []
        move_line_env = self.env["stock.move.line"].sudo()
        move_lines = move_line_env.search([("picking_id", "in", picking_ids), ("product_id", "!=", False)], order="date desc, id desc")
        package_ids = set(move_lines.mapped("package_id").ids + move_lines.mapped("result_package_id").ids)
        info_by_package = portal_package_shipping_map(self.env, list(package_ids))
        rows = []
        seen = set()
        for move_line in move_lines:
            lot = move_line.lot_id
            product = move_line.product_id
            package = move_line.package_id or move_line.result_package_id
            if product.tracking == "serial" and lot:
                key = ("serial", lot.name, product.id)
                quantity = 1
                sn_code = lot.name or ""
            else:
                key = ("move_line", move_line.id)
                quantity = move_line.quantity
                sn_code = ""
            if key in seen:
                continue
            seen.add(key)
            info = info_by_package.get(package.id, {}) if package else {}
            rows.append({
                "outbound_no": order.billno or order.reference or "",
                "bl_no": (lot.bill_of_lading if lot else "") or info.get("bl_no") or "",
                "container_no": (lot.cntrno if lot else "") or info.get("container_no") or "",
                "package_name": package.name if package else "",
                "product_code": portal_product_code(product),
                "product_name": portal_product_name(product),
                "quantity": quantity,
                "sn_code": sn_code,
                "scan_time": portal_format_datetime(move_line.date or move_line.picking_id.date_done),
            })
        return rows

    @api.model
    def get_outbound_detail_grouped(self, outbound_id):
        order = self.get_outbound_order(outbound_id)
        if not order:
            return []
        products_by_id = {}
        for line in order.outbound_order_product_ids:
            product = line.product_id
            if not product:
                continue
            product_row = products_by_id.setdefault(product.id, {"product_code": portal_product_code(product), "product_name": portal_product_name(product), "quantity": 0.0})
            product_row["quantity"] += line.quantity or 0.0
        products = list(products_by_id.values())
        if not products:
            return []
        return [{"outbound_no": order.billno or order.reference or "", "total_quantity": sum(product["quantity"] for product in products), "products": products}]
