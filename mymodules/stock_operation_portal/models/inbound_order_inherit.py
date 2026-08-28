# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .utils import portal_attachment_row, portal_detect_attachment_type, portal_doc_binary_row, portal_product_code, portal_project_domain


class InboundOrder(models.Model):
    _inherit = 'world.depot.inbound.order'

    stock_operation_portal_confirmed = fields.Boolean(string='Portal Confirmed', readonly=True, copy=False, index=True, tracking=True)
    stock_operation_portal_confirm_user_id = fields.Many2one('res.users', string='Portal Confirmed By', readonly=True, copy=False, tracking=True)
    stock_operation_portal_confirm_time = fields.Datetime(string='Portal Confirmed At', readonly=True, copy=False, tracking=True)

    @api.model
    def get_inbound_detail(self, inbound_id):
        order = self.get_inbound_order(inbound_id)
        if not order:
            return []
        move_line_env = self.env["stock.move.line"].sudo()
        move_lines = move_line_env.search(
            [("picking_id.inbound_order_id", "=", order.id), ("result_package_id", "!=", False),
             ("product_id", "!=", False)],
            order="result_package_id, product_id, id",
        )
        if not move_lines and order.stock_picking_id:
            move_lines = move_line_env.search(
                [("picking_id", "=", order.stock_picking_id.id), ("result_package_id", "!=", False),
                 ("product_id", "!=", False)],
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
    def get_inbound_detail_grouped(self, inbound_id):
        order = self.get_inbound_order(inbound_id)
        if not order:
            return []
        move_line_env = self.env["stock.move.line"].sudo()
        product_env = self.env["product.product"].sudo()

        domain = [
            ("picking_id.inbound_order_id", "=", order.id),
            ("result_package_id", "!=", False),
            ("product_id", "!=", False),
        ]
        groups = move_line_env.read_group(
            domain,
            ["quantity_sum:sum(quantity)"],
            ["result_package_id", "product_id"],
            lazy=False,
        )
        if not groups and order.stock_picking_id:
            domain = [
                ("picking_id", "=", order.stock_picking_id.id),
                ("result_package_id", "!=", False),
                ("product_id", "!=", False),
            ]
            groups = move_line_env.read_group(
                domain,
                ["quantity_sum:sum(quantity)"],
                ["result_package_id", "product_id"],
                lazy=False,
            )

        if groups:
            product_ids = [group["product_id"][0] for group in groups if group.get("product_id")]
            products_by_id = {product.id: product for product in product_env.browse(product_ids)}

            grouped_rows = {}

            for group in groups:
                package_data = group.get("result_package_id")
                product_data = group.get("product_id")

                if not package_data or not product_data:
                    continue

                package_id = package_data[0]
                package_name = package_data[1]
                product_id = product_data[0]
                product = products_by_id.get(product_id)

                package_row = grouped_rows.setdefault(package_id, {
                    "package_name": package_name or "",
                    "container_no": order.cntr_no or "",
                    "bl_no": order.bl_no or "",
                    "total_quantity": 0.0,
                    "products": [],
                })

                quantity = group.get("quantity_sum") or 0.0

                package_row["products"].append({
                    "product_code": portal_product_code(product) if product else "",
                    "product_name": product.display_name if product else product_data[1],
                    "quantity": quantity,
                })
                package_row["total_quantity"] += quantity

            return list(grouped_rows.values())

        grouped_rows = {}
        for line in order.inbound_order_product_ids:
            package_row = grouped_rows.setdefault(line.pallet_no or "", {
                "package_name": line.pallet_no or "",
                "container_no": order.cntr_no or "",
                "bl_no": order.bl_no or "",
                "total_quantity": 0.0,
                "products": [],
            })
            for product_line in line.inbound_order_product_pallet_ids:
                product = product_line.product_id
                quantity = (product_line.quantity or 0.0) * (line.pallets or 0.0)
                package_row["products"].append({
                    "product_code": portal_product_code(product),
                    "product_name": product.display_name or product.name or "",
                    "quantity": quantity,
                })
                package_row["total_quantity"] += quantity
        return list(grouped_rows.values())

    @api.model
    def get_inbound_attachments(self, inbound_id):
        order = self.get_inbound_order(inbound_id)
        if not order:
            return []

        doc_env = self.env["world.depot.inbound.order.docs"].sudo()
        attachment_env = self.env["ir.attachment"].sudo()

        docs = doc_env.search([("inbound_order_id", "=", order.id)], order="id desc")
        doc_by_filename = {doc.filename: doc for doc in docs if doc.filename}

        attachment_domain = [
            ("res_model", "=", "world.depot.inbound.order"),
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

        for doc in docs:
            if doc.filename and doc.file and doc.filename not in seen_names:
                rows.append(portal_doc_binary_row(doc, portal_detect_attachment_type(doc.filename, doc.doc_type)))
                seen_names.add(doc.filename)

        return rows

    @api.model
    def get_inbound_order(self, inbound_id):
        if not inbound_id:
            return self.env["world.depot.inbound.order"].sudo()
        domain = [("id", "=", inbound_id)] + portal_project_domain(self.env, "project")
        return self.env["world.depot.inbound.order"].sudo().search(domain, limit=1)
