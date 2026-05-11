# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.osv import expression

from .utils import (
    portal_apply_date_filters,
    portal_attachment_row,
    portal_detect_attachment_type,
    portal_doc_binary_row,
    portal_filter_value,
    portal_format_date,
portal_format_datetime,
    portal_owner_domain,
    portal_product_code,
)


class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"

    @api.model
    def get_inbound_list(self, filters=None, offset=0, limit=0):
        filters = filters or {}
        domain = portal_owner_domain(self.env, "project.owner")
        inbound_no = portal_filter_value(filters, "inbound_no", "reference")
        container_no = filters.get("container_no")
        bl_no = filters.get("bl_no")
        portal_inbound_status = filters.get("portal_inbound_status")
        domain.append(("state", "=", "confirm"))
        if inbound_no:
            domain = expression.AND([domain, ["|", ("billno", "ilike", inbound_no), ("reference", "ilike", inbound_no)]])
        if bl_no:
            domain.append(("bl_no", "ilike", bl_no))
        if container_no:
            domain.append(("cntr_no", "ilike", container_no))

        if portal_inbound_status == "inbound_confirmed":
            domain.append(("stock_picking_id", "=", False))
        elif portal_inbound_status == "inbound_processing":
            domain += [("stock_picking_id", "!=", False), ("stock_picking_id.state", "!=", "done")]
        elif portal_inbound_status == "inbound_done":
            domain.append(("stock_picking_id.state", "=", "done"))

        portal_apply_date_filters(domain, filters, "i_datetime", ("inbound_date_from",), ("inbound_date_to",))
        inbound_env = self.env["world.depot.inbound.order"].sudo()
        orders = inbound_env.search(domain, order="i_datetime desc, a_date desc, date desc, id desc", offset=offset, limit=limit)
        rows = []
        for rec in orders:
            picking = rec.stock_picking_id
            if picking and picking.state == "done":
                state = "inbound_done"
            elif picking:
                state = "inbound_processing"
            else:
                state = "inbound_confirmed"

            total_quantity = sum(line.quantity for line in rec.inbound_order_product_ids)
            total_pallets = rec.pallets or sum(line.pallets for line in rec.inbound_order_product_ids)
            rows.append({
                "inbound_id": rec.id,
                "inbound_no": rec.billno or "",
                "reference": rec.reference or "",
                "bl_no": rec.bl_no or "",
                "container_no": rec.cntr_no or "",
                "inbound_date": portal_format_datetime(rec.i_datetime or rec.a_date or rec.date),
                "portal_inbound_status": state,
                "total_quantity": total_quantity,
                "total_pallets": total_pallets,
            })
        return rows

    @api.model
    def get_inbound_detail(self, inbound_id):
        order = self.get_inbound_order(inbound_id)
        if not order:
            return []
        move_line_env = self.env["stock.move.line"].sudo()
        move_lines = move_line_env.search(
            [("picking_id.inbound_order_id", "=", order.id), ("result_package_id", "!=", False), ("product_id", "!=", False)],
            order="result_package_id, product_id, id",
        )
        if not move_lines and order.stock_picking_id:
            move_lines = move_line_env.search(
                [("picking_id", "=", order.stock_picking_id.id), ("result_package_id", "!=", False), ("product_id", "!=", False)],
                order="result_package_id, product_id, id",
            )
        rows_by_key = {}
        for move_line in move_lines:
            package = move_line.result_package_id
            product = move_line.product_id
            key = (package.id, product.id)
            row = rows_by_key.setdefault(key, {
                "package_name": package.name or "",
                "container_no": order.cntr_no or "",
                "bl_no": order.bl_no or "",
                "product_code": portal_product_code(product),
                "product_name": product.display_name or product.name or "",
                "quantity": 0.0,
            })
            row["quantity"] += move_line.quantity
        if rows_by_key:
            return list(rows_by_key.values())
        rows = []
        for line in order.inbound_order_product_ids:
            for product_line in line.inbound_order_product_pallet_ids:
                product = product_line.product_id
                rows.append({
                    "package_name": line.pallet_no or "",
                    "container_no": order.cntr_no or "",
                    "bl_no": order.bl_no or "",
                    "product_code": portal_product_code(product),
                    "product_name": product.display_name or product.name or "",
                    "quantity": (product_line.quantity or 0.0) * (line.pallets or 0.0),
                })
        return rows

    @api.model
    def get_inbound_attachments(self, inbound_id):
        order = self.get_inbound_order(inbound_id)
        if not order:
            return []
        doc_env = self.env["world.depot.inbound.order.docs"].sudo()
        attachment_env = self.env["ir.attachment"].sudo()
        docs = doc_env.search([("inbound_order_id", "=", order.id)], order="id desc")
        attachment_domain = [("res_model", "=", "world.depot.inbound.order"), ("res_id", "=", order.id)]
        if docs:
            attachment_domain = expression.OR([
                attachment_domain,
                [("res_model", "=", "world.depot.inbound.order.docs"), ("res_id", "in", docs.ids)],
            ])
        attachments = attachment_env.search(attachment_domain, order="id desc")
        rows = []
        seen_names = set()
        for attachment in attachments:
            row = portal_attachment_row(attachment)
            rows.append(row)
            seen_names.add(row["file_name"])
        for doc in docs:
            if doc.filename and doc.filename not in seen_names and doc.file:
                rows.append(portal_doc_binary_row(doc, portal_detect_attachment_type(doc.filename, doc.doc_type)))
        return rows

    @api.model
    def get_inbound_order(self, inbound_id):
        if not inbound_id:
            return self.env["world.depot.inbound.order"].sudo()
        domain = [("id", "=", inbound_id)] + portal_owner_domain(self.env, "project.owner")
        return self.env["world.depot.inbound.order"].sudo().search(domain, limit=1)
