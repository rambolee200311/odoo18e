# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, models
from odoo.osv import expression

from .utils import (
    portal_apply_date_filters,
    portal_attachment_row,
    portal_binary_field_row,
    portal_detect_attachment_type,
    portal_doc_binary_row,
    portal_filter_value,
    portal_format_date,
    portal_format_datetime,
    portal_owner_domain,
    portal_package_container_from_name,
    portal_package_shipping_map,
    portal_product_code,
)


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    @api.model
    def get_outbound_list(self, filters=None, offset=0, limit=0):
        filters = filters or {}
        domain = portal_owner_domain(self.env, "project.owner")
        outbound_no = portal_filter_value(filters, "outbound_no", "billno", "reference")
        status = portal_filter_value(filters, "status")
        if outbound_no:
            domain = expression.AND([domain, ["|", ("billno", "ilike", outbound_no), ("reference", "ilike", outbound_no)]])
        if status:
            domain.append(("status", "=", status))
        portal_apply_date_filters(domain, filters, "o_date", ("date_from", "outbound_date_from"), ("date_to", "outbound_date_to"))
        outbound_env = self.env["world.depot.outbound.order"].sudo()
        orders = outbound_env.search(domain, order="o_date desc, picking_Out_date desc, date desc, id desc", offset=offset, limit=limit)
        shipping_by_order = self.get_outbound_shipping_map(orders)
        container_no = portal_filter_value(filters, "container_no", "cntr_no")
        bl_no = portal_filter_value(filters, "bl_no")
        rows = []
        for rec in orders:
            shipping = shipping_by_order.get(rec.id, {"containers": set(), "bls": set()})
            containers = set(line.cntr_no for line in rec.outbound_order_product_ids if line.cntr_no)
            containers.update(shipping["containers"])
            bls = shipping["bls"]
            if container_no and not any(container_no.lower() in item.lower() for item in containers):
                continue
            if bl_no and not any(bl_no.lower() in item.lower() for item in bls):
                continue
            total_quantity = sum(line.quantity for line in rec.outbound_order_product_ids)
            rows.append({
                "outbound_id": rec.id,
                "outbound_no": rec.billno or rec.reference or "",
                "bl_no": ", ".join(sorted(bls)),
                "container_no": ", ".join(sorted(containers)),
                "outbound_date": portal_format_date(rec.o_date or rec.picking_Out_date or rec.picking_PICK_date or rec.date),
                "state": rec.status or rec.state or "",
                "total_quantity": total_quantity,
                "picking_no": rec.picking_PICK.name or "",
            })
        return rows

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
                "bl_no": lot.bill_of_lading or "",
                "container_no": lot.cntrno or "",
                "package_name": "",
                "product_code": portal_product_code(product),
                "product_name": product.display_name or detail.product_name or "",
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
        attachment_domain = [("res_model", "=", "world.depot.outbound.order"), ("res_id", "=", order.id)]
        if docs:
            attachment_domain = expression.OR([
                attachment_domain,
                [("res_model", "=", "world.depot.outbound.order.docs"), ("res_id", "in", docs.ids)],
            ])
        attachments = attachment_env.search(attachment_domain, order="id desc")
        rows = []
        seen_names = set()
        for attachment in attachments:
            datas_fname = attachment.datas_fname if "datas_fname" in attachment._fields else ""
            row = portal_attachment_row(attachment, portal_detect_attachment_type(attachment.name or datas_fname))
            rows.append(row)
            seen_names.add(row["file_name"])
        pod_row = portal_binary_field_row(order, "pod_file", "pod_filename", "POD")
        if pod_row and pod_row["file_name"] not in seen_names:
            rows.append(pod_row)
            seen_names.add(pod_row["file_name"])
        for doc in docs:
            if doc.filename and doc.filename not in seen_names and doc.file:
                rows.append(portal_doc_binary_row(doc, portal_detect_attachment_type(doc.filename, doc.doc_type)))
        return rows

    @api.model
    def get_outbound_order(self, outbound_id):
        if not outbound_id:
            return self.env["world.depot.outbound.order"].sudo()
        domain = [("id", "=", outbound_id)] + portal_owner_domain(self.env, "project.owner")
        return self.env["world.depot.outbound.order"].sudo().search(domain, limit=1)

    @api.model
    def get_outbound_shipping_map(self, orders):
        result = defaultdict(lambda: {"containers": set(), "bls": set()})
        picking_to_order = {}
        for rec in orders:
            if rec.picking_PICK:
                picking_to_order[rec.picking_PICK.id] = rec.id
            if rec.picking_Out:
                picking_to_order[rec.picking_Out.id] = rec.id
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
        move_lines = move_line_env.search(
            [("picking_id", "in", picking_ids), ("product_id", "!=", False), ("lot_id", "!=", False)],
            order="date desc, id desc",
        )
        package_ids = set(move_lines.mapped("package_id").ids + move_lines.mapped("result_package_id").ids)
        info_by_package = portal_package_shipping_map(self.env, list(package_ids))
        rows = []
        seen = set()
        for move_line in move_lines:
            lot = move_line.lot_id
            product = move_line.product_id
            key = (lot.name, product.id)
            if key in seen:
                continue
            seen.add(key)
            package = move_line.package_id or move_line.result_package_id
            info = info_by_package.get(package.id, {}) if package else {}
            container_no = lot.cntrno or info.get("container_no") or portal_package_container_from_name(package.name if package else "")
            bl_no = lot.bill_of_lading or info.get("bl_no") or ""
            rows.append({
                "outbound_no": order.billno or order.reference or "",
                "bl_no": bl_no,
                "container_no": container_no,
                "package_name": package.name if package else "",
                "product_code": portal_product_code(product),
                "product_name": product.display_name or product.name or "",
                "quantity": 1,
                "sn_code": lot.name or "",
                "scan_time": portal_format_datetime(move_line.date or move_line.picking_id.date_done),
            })
        return rows
