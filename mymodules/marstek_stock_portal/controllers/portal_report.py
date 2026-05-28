# -*- coding: utf-8 -*-

import csv
import io

from odoo import http
from odoo.http import content_disposition, request
from werkzeug.exceptions import BadRequest, NotFound


class MarstekPortalReport(http.Controller):

    allowed_page_types = ("stock", "container_stock", "inbounds", "outbounds","outbound_sn")
    allowed_export_formats = ("csv", "pdf")

    filter_fields_by_page_type = {
        "stock": ("container_no", "bl_no", "product_code", "date_from", "date_to"),
        "container_stock": ("container_no",),
        "inbounds": (
            "inbound_no",
            "reference",
            "bl_no",
            "container_no",
            "portal_inbound_status",
            "inbound_date_from",
            "inbound_date_to",
        ),
        "outbounds": (
            "outbound_no",
            "bl_no",
            "container_no",
            "portal_outbound_status",
            "outbound_date_from",
            "outbound_date_to",
        ),
        "outbound_sn": ("outbound_id",),
    }

    csv_headers_by_page_type = {
        "stock": ["Pallet No", "Container No", "BL No", "Product Code", "Product Name", "Quantity", "Location", "Inbound Date"],
        "container_stock": ["Container No", "BL No", "Total Quantity", "Pallet Count", "Pallet No", "Product", "Quantity", "Location", "Inbound Date"],
        "inbounds": ["Inbound No", "Reference", "BL No", "Container No", "Inbound Date", "Status", "Total Quantity", "Pallet Count"],

        "outbound_sn": ["Outbound Order", "Project", "Type", "Outbound Reference", "Date", "Picking", "Product", "Product Name", "Serial/Lot Name", "Quantity"], }

    pdf_report_xmlid_by_page_type = {
        "stock": "marstek_stock_portal.report_marstek_stock_export_pdf",
        "container_stock": "marstek_stock_portal.report_marstek_container_stock_export_pdf",
        "inbounds": "marstek_stock_portal.report_marstek_inbounds_export_pdf",
        "outbounds": "marstek_stock_portal.report_marstek_outbounds_export_pdf",
    }

    def marstek_filter_values(self, kw, page_type):
        filters = {}
        for name in self.filter_fields_by_page_type.get(page_type, ()):
            value = kw.get(name)
            if isinstance(value, str):
                value = value.strip()
            filters[name] = value or ""
        return filters

    def get_export_data(self, page_type, filters):
        if page_type == "stock":
            rows = request.env["stock.quant.package"].get_all_stock(filters)
            return self.stock_export_lines(rows)

        if page_type == "container_stock":
            stock_result = {"container_no": filters.get("container_no") or "", "bl_no": "", "total_quantity": 0.0, "lines": []}
            if filters.get("container_no"):
                stock_result = request.env["stock.quant.package"].get_stock_by_container_no(filters.get("container_no"))
            return self.container_stock_export_lines(stock_result)

        if page_type == "inbounds":
            rows = request.env["world.depot.inbound.order"].get_inbound_list(filters)
            return self.inbound_export_lines(rows)

        if page_type == "outbounds":
            rows = request.env["world.depot.outbound.order"].get_outbound_list(filters)
            return self.outbound_export_lines(rows)

        if page_type == "outbound_sn":
            outbound_id = int(filters.get("outbound_id") or 0)
            rows = request.env["world.depot.outbound.order"].get_outbound_sn_export_rows(outbound_id)
            return self.outbound_sn_export_lines(rows)
        return []

    def stock_export_lines(self, rows):
        return [[
            row.get("package_name", ""),
            row.get("container_no", ""),
            row.get("bl_no", ""),
            row.get("product_code", ""),
            row.get("product_name", ""),
            row.get("quantity", 0),
            row.get("location_name", ""),
            row.get("inbound_date", ""),
        ] for row in rows]

    def container_stock_export_lines(self, stock_result):
        rows = stock_result.get("lines", [])
        package_names = {row.get("package_name") for row in rows if row.get("package_name")}
        pallet_count = len(package_names)
        total_quantity = stock_result.get("total_quantity", 0)
        container_no = stock_result.get("container_no", "")
        bl_no = stock_result.get("bl_no", "")
        return [[
            row.get("container_no") or container_no,
            row.get("bl_no") or bl_no,
            total_quantity,
            pallet_count,
            row.get("package_name", ""),
            row.get("product_name", ""),
            row.get("quantity", 0),
            row.get("location_name", ""),
            row.get("inbound_date", ""),
        ] for row in rows]

    def inbound_export_lines(self, rows):
        return [[
            row.get("inbound_no", ""),
            row.get("reference", ""),
            row.get("bl_no", ""),
            row.get("container_no", ""),
            row.get("inbound_date", ""),
            row.get("portal_inbound_status") or row.get("state", ""),
            row.get("total_quantity", 0),
            row.get("total_pallets", 0),
        ] for row in rows]

    def outbound_export_lines(self, rows):
        return [[
            row.get("outbound_no", ""),
            row.get("bl_no", ""),
            row.get("container_no", ""),
            row.get("outbound_date", ""),
            row.get("portal_outbound_status") or row.get("state", ""),
            row.get("total_quantity", 0),
            row.get("picking_no", ""),
        ] for row in rows]

    def outbound_sn_export_lines(self, rows):
        return [[
            row.get("outbound_no", ""),
            row.get("project_name", ""),
            row.get("type", ""),
            row.get("reference", ""),
            row.get("outbound_date", ""),
            row.get("picking_no", ""),
            row.get("product_code", ""),
            row.get("product_name", ""),
            row.get("sn_code", ""),
            row.get("quantity", 0),
        ] for row in rows]
    def make_csv_response(self, page_type, headers, rows):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        csv_data = output.getvalue().encode("utf-8-sig")
        return request.make_response(
            csv_data,
            headers=[
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition", content_disposition(f"marstek_{page_type}.csv")),
            ],
        )

    def make_pdf_response(self, page_type, rows):
        view_xmlid = self.pdf_report_xmlid_by_page_type[page_type]
        # 直接渲染 HTML 模板
        html = request.env["ir.ui.view"].sudo()._render_template(
            view_xmlid,
            {"docs": rows}
        )
        # 使用 Odoo 的报告服务生成 PDF
        pdf = request.env["ir.actions.report"].sudo()._run_wkhtmltopdf([html])
        return request.make_response(
            pdf,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Disposition", content_disposition(f"marstek_{page_type}.pdf")),
            ],
        )

    @http.route("/my/marstek/export/<string:page_type>/<string:export_format>", type="http", auth="user", website=True)
    def marstek_export(self, page_type, export_format, **kw):
        if page_type not in self.allowed_page_types:
            raise NotFound()
        if export_format not in self.allowed_export_formats:
            raise BadRequest()

        filters = self.marstek_filter_values(kw, page_type)
        rows = self.get_export_data(page_type, filters)

        if export_format == "csv":
            headers = self.csv_headers_by_page_type[page_type]
            return self.make_csv_response(page_type, headers, rows)
        return self.make_pdf_response(page_type, rows)
