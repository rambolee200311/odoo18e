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
        outbound_no = portal_filter_value(filters, "outbound_no", "reference")
        portal_outbound_status = filters.get("portal_outbound_status")
        container_no = filters.get("container_no")
        bl_no = filters.get("bl_no")
        vsourcebillcode = filters.get("vsourcebillcode")
        cprojectid = filters.get("cprojectid")
        domain.append(("state", "=", "confirm"))
        # if bl_no:
        #     domain.append(("bl_no", "ilike", bl_no))
        # if container_no:
        #     domain.append(("cntr_no", "ilike", container_no))
        if outbound_no:
            domain = expression.AND([domain, ["|", ("billno", "ilike", outbound_no), ("reference", "ilike", outbound_no)]])
        if vsourcebillcode:
            domain = expression.AND([domain, ["|", ("vsourcebillcode", "ilike", vsourcebillcode), ("outbound_order_product_ids.cprojectid", "ilike", vsourcebillcode)]])
        if cprojectid:
            domain.append(("outbound_order_product_ids.cprojectid", "ilike", cprojectid))

        if portal_outbound_status == "outbound_confirmed":
            domain.append(("picking_PICK", "=", False))
        elif portal_outbound_status == "outbound_picking_processing":
            domain += [("picking_PICK", "!=", False), ("picking_PICK.state", "!=", "done")]
        elif portal_outbound_status == "outbound_picking_done":
            domain.append(("picking_PICK.state", "=", "done"))
        portal_apply_date_filters(domain, filters, "picking_PICK_date", ("outbound_date_from",), ("outbound_date_to",))
        outbound_env = self.env["world.depot.outbound.order"].sudo()
        orders = outbound_env.search(domain, order="o_date desc, picking_Out_date desc, date desc, id desc", offset=offset, limit=limit)
        shipping_by_order = self.get_outbound_shipping_map(orders)


        rows = []
        for rec in orders:
            picking = rec.picking_PICK
            if picking and picking.state == "done":
                state = "outbound_picking_done"
            elif picking:
                state = "outbound_picking_processing"
            else:
                state = "outbound_confirmed"
            shipping = shipping_by_order.get(rec.id, {"containers": set(), "bls": set()})
            containers = set(shipping["containers"])
            bls = shipping["bls"]
            if container_no and not any(container_no.lower() in item.lower() for item in containers):
                continue
            if bl_no and not any(bl_no.lower() in item.lower() for item in bls):
                continue
            #total_pallets = sum(line.pallets for line in rec.outbound_order_product_ids)
            total_quantity = sum(line.quantity for line in rec.outbound_order_product_ids)

            # package_names = []
            # if rec.picking_PICK:
            #     package_names = rec.picking_PICK.move_line_ids.mapped("package_id.name")
            #     package_names += rec.picking_PICK.move_line_ids.mapped("result_package_id.name")
            #     package_names = [name for name in package_names if name]
            # first_package_name = package_names[0] if package_names else ""
            # pallet_summary = f"{first_package_name},etc.{total_pallets}Pallet" if first_package_name else ""


            product_names = rec.outbound_order_product_ids.mapped("product_id.name")
            contract_no = ", ".join(dict.fromkeys(filter(None, rec.outbound_order_product_ids.mapped("cprojectid"))))

            first_product_name = product_names[0] if product_names else ""
            product_summary = f"{first_product_name},  etc.({total_quantity} pcs)" if first_product_name else ""
            rows.append({
                "outbound_id": rec.id,
                "outbound_no": rec.billno or rec.reference or "",
                "contract_no": contract_no,
                "reference": rec.reference or "",
                "bl_no": ", ".join(sorted(bls)),
                "container_no": ", ".join(sorted(containers)),
                "outbound_date": portal_format_date(rec.picking_PICK_date),
                "portal_outbound_status": state,
                #"total_pallets":total_pallets,
                "total_quantity": total_quantity,
                "picking_no": rec.picking_PICK.name or "",
                #"pallet_summary": pallet_summary,
                "product_summary": product_summary,
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
                "reference": order.reference or "",
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
        doc_by_filename = {doc.filename: doc for doc in docs if doc.filename}

        attachment_domain = [
            ("res_model", "=", "world.depot.outbound.order"),
            ("res_id", "=", order.id),
            ("res_field", "=", False),
        ]
        attachments = attachment_env.search(attachment_domain, order="id desc")

        rows = []
        seen_names = set()

        for attachment in attachments:
            datas_fname = attachment.datas_fname if "datas_fname" in attachment._fields else ""
            file_name = attachment.name or datas_fname or ""
            doc = doc_by_filename.get(file_name)
            file_type = portal_detect_attachment_type(file_name,
                                                      doc.doc_type) if doc else portal_detect_attachment_type(file_name)
            row = portal_attachment_row(attachment, file_type)
            rows.append(row)
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
            [("picking_id", "in", picking_ids), ("product_id", "!=", False)],
            order="date desc, id desc",
        )

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
            container_no = (lot.cntrno if lot else "") or info.get("container_no")
            bl_no = (lot.bill_of_lading if lot else "") or info.get("bl_no") or ""

            rows.append({
                "outbound_no": order.billno or order.reference or "",
                "bl_no": bl_no,
                "container_no": container_no,
                "package_name": package.name if package else "",
                "product_code": portal_product_code(product),
                "product_name": product.display_name or product.name or "",
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

            product_row = products_by_id.setdefault(product.id, {
                "product_code": portal_product_code(product),
                "product_name": product.display_name or product.name or "",
                "quantity": 0.0,
            })
            product_row["quantity"] += line.quantity or 0.0

        products = list(products_by_id.values())
        if not products:
            return []

        return [{
            "outbound_no": order.billno or order.reference or "",
            "total_quantity": sum(product["quantity"] for product in products),
            "products": products,
        }]

    @api.model
    @api.model
    def get_outbound_sn_export_rows(self, outbound_id):
        order = self.get_outbound_order(outbound_id)
        if not order:
            return []

        rows = self.get_outbound_detail(outbound_id)

        outbound_date = portal_format_date(
            order.picking_PICK.date_done
            or order.picking_PICK_date
            or order.o_date
            or order.date
        )

        result = []
        for row in rows:
            if not row.get("sn_code"):
                continue

            row.update({
                "project_name": order.project.name or "",
                "type": order.type or "",
                "reference": order.reference or "",
                "outbound_date": outbound_date,
                "picking_no": order.picking_PICK.name or "",
            })
            result.append(row)

        return result



