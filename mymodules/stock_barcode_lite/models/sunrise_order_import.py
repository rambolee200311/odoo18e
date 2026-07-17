# -*- coding: utf-8 -*-

import math
import os
from datetime import datetime
from io import BytesIO

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import xlrd
except ImportError:
    xlrd = None


class SunriseOrderImport(models.Model):
    _name = "stock.barcode.lite.sunrise.order.import"
    _description = "Sunrise Order Import"
    _order = "id desc"

    name = fields.Char(string="Name", required=True, copy=False, index=True)
    import_type = fields.Selection([("inbound", "Inbound"), ("outbound", "Outbound")], string="Import Type", required=True, copy=False, index=True)
    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", copy=False, index=True)
    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", copy=False, index=True)
    filename = fields.Char(string="Filename", copy=False)
    state = fields.Selection([("draft", "Draft"), ("done", "Done"), ("partial", "Partial"), ("failed", "Failed")], string="State", default="draft", required=True, copy=False, index=True)
    total_count = fields.Integer(string="Total Count", copy=False)
    success_count = fields.Integer(string="Success Count", copy=False)
    failed_count = fields.Integer(string="Failed Count", copy=False)
    message = fields.Text(string="Message", copy=False)
    import_line_ids = fields.One2many("stock.barcode.lite.sunrise.order.import.line", "import_id", string="Import Lines", copy=False)

    def read_excel_rows(self, file_content, filename):
        extension = os.path.splitext(filename or "")[1].lower()
        if extension not in (".xlsx", ".xls"):
            raise UserError(_("Only .xlsx and .xls files are supported."))

        def append_row(rows, header_map, row_values, row_number):
            if not any(self.cell_to_text(value) for value in row_values):
                return
            row_data = {}
            for header, index in header_map.items():
                row_data[header] = row_values[index] if index < len(row_values) else ""
            rows.append((row_number, row_data))

        if extension == ".xlsx":
            if openpyxl is None:
                raise UserError(_("openpyxl is required to import .xlsx files."))
            workbook = openpyxl.load_workbook(BytesIO(file_content), read_only=True, data_only=True)
            sheet = workbook.active
            rows_iter = sheet.iter_rows(values_only=True)
            try:
                header_row = next(rows_iter)
            except StopIteration:
                raise UserError(_("The Excel file is empty."))
            header_map = self.get_header_map(header_row)
            rows = []
            for row_number, row_values in enumerate(rows_iter, start=2):
                append_row(rows, header_map, row_values, row_number)
            return rows

        if xlrd is None:
            raise UserError(_("xlrd is required to import .xls files."))
        workbook = xlrd.open_workbook(file_contents=file_content)
        if workbook.nsheets < 1:
            raise UserError(_("The Excel file is empty."))
        sheet = workbook.sheet_by_index(0)
        if sheet.nrows < 1:
            raise UserError(_("The Excel file is empty."))
        header_map = self.get_header_map(sheet.row_values(0))
        rows = []
        for row_index in range(1, sheet.nrows):
            append_row(rows, header_map, sheet.row_values(row_index), row_index + 1)
        return rows

    def get_header_map(self, header_row):
        header_map = {}
        for index, value in enumerate(header_row):
            header = self.get_header_key(value)
            if header and header not in header_map:
                header_map[header] = index
        if not header_map:
            raise UserError(_("No supported Excel headers were found."))
        return header_map

    def get_header_key(self, value):
        text = self.cell_to_text(value).strip()
        if not text:
            return False
        supported_fields = self.get_supported_fields()
        normalized_text = text.replace("（", "(").replace("）", ")")
        lower_text = normalized_text.lower()
        if lower_text in supported_fields:
            return lower_text
        if "(" in lower_text and ")" in lower_text:
            before = lower_text.split("(", 1)[0].strip()
            inside = lower_text.split("(", 1)[1].split(")", 1)[0].strip()
            if before in supported_fields:
                return before
            if inside in supported_fields:
                return inside
        chinese_headers = self.get_chinese_headers()
        return chinese_headers.get(normalized_text) or chinese_headers.get(lower_text)

    def get_supported_fields(self):
        return {
            "ref", "reference", "cntr_no", "inbound_cntr_no", "cwarehouseid", "product", "product_name", "product_ean",
            "lot_name", "pallet_no", "package_barcode", "cspaceid", "box_qty", "box_in_qty", "box_type",
            "ninnum", "castunitid", "u8_aux_uom_name", "u8_aux_qty", "u8_conversion_rate", "vsourcebillcode",
            "vsourcerowno", "cprojectid", "ndiscounttaxtype", "is_lot", "de_palletize", "m_date", "e_date", "remark",
        }

    def get_chinese_headers(self):
        return {
            "ref": "reference",
            "唯一标识": "reference",
            "集装箱号": "cntr_no",
            "入库集装箱号": "inbound_cntr_no",
            "u8c仓库编码": "cwarehouseid",
            "u8c 仓库编码": "cwarehouseid",
            "产品编码": "product",
            "产品名称": "product_name",
            "产品条码": "product_ean",
            "批次号": "lot_name",
            "托盘号": "pallet_no",
            "货位号": "cspaceid",
            "箱数": "box_qty",
            "箱内产品数": "box_in_qty",
            "箱类型": "box_type",
            "产品总数量": "ninnum",
            "数产品总数量": "ninnum",
            "辅单位编码": "castunitid",
            "计量单位名称": "u8_aux_uom_name",
            "计量单位单位名称": "u8_aux_uom_name",
            "辅数量": "u8_aux_qty",
            "换算率": "u8_conversion_rate",
            "单据号": "vsourcebillcode",
            "来源单据行号": "vsourcerowno",
            "合同号": "cprojectid",
            "扣税类别": "ndiscounttaxtype",
            "是否批次": "is_lot",
            "是否拆托": "de_palletize",
            "生产日期": "m_date",
            "有效期": "e_date",
            "备注": "remark",
        }

    def cell_to_text(self, value):
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    def process_import(self, file_content, filename):
        line_model = self.env["stock.barcode.lite.sunrise.order.import.line"]
        for rec in self:
            try:
                rows = rec.read_excel_rows(file_content, filename)
            except Exception as error:
                rec.write({"state": "failed", "message": _("Import failed while reading Excel: %s") % str(error)})
                raise
            if not rows:
                rec.write({"state": "failed", "message": _("The Excel file has no data rows.")})
                raise UserError(_("The Excel file has no data rows."))

            for row_number, row_data in rows:
                line = line_model.create(rec.get_import_line_values(row_number, row_data))
                try:
                    with rec.env.cr.savepoint():
                        line.process_import_line()
                except Exception as error:
                    line.write({"state": "failed", "error_msg": str(error)})
            rec.refresh_result_counts()
        return True

    def get_import_line_values(self, row_number, row_data):
        self.ensure_one()
        values = {"name": "%s Row %s" % (self.name, row_number), "import_id": self.id, "row_number": row_number}
        for field_name in self.get_supported_fields():
            if field_name == "ref":
                continue
            if field_name in self.env["stock.barcode.lite.sunrise.order.import.line"]._fields:
                values[field_name] = self.cell_to_text(row_data.get(field_name))
        if row_data.get("ref") and not values.get("reference"):
            values["reference"] = self.cell_to_text(row_data.get("ref"))
        return values

    def refresh_result_counts(self):
        for rec in self:
            success_count = len(rec.import_line_ids.filtered(lambda line: line.state == "success"))
            failed_count = len(rec.import_line_ids.filtered(lambda line: line.state == "failed"))
            total_count = len(rec.import_line_ids)
            if success_count and failed_count:
                state = "partial"
            elif success_count:
                state = "done"
            else:
                state = "failed"
            rec.write({
                "state": state,
                "total_count": total_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "message": _("Import finished. Success: %(success)s, Failed: %(failed)s") % {"success": success_count, "failed": failed_count},
            })

    def action_retry_failed_lines(self):
        for rec in self:
            failed_lines = rec.import_line_ids.filtered(lambda line: line.state == "failed")
            if not failed_lines:
                raise UserError(_("There are no failed import lines to retry."))
            failed_lines.action_retry_import()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": _("Retry Import"), "message": _("Retry finished."), "type": "success", "sticky": False},
        }


class SunriseOrderImportLine(models.Model):
    _name = "stock.barcode.lite.sunrise.order.import.line"
    _description = "Sunrise Order Import Line"
    _order = "id desc"

    name = fields.Char(string="Name", copy=False, index=True)
    import_id = fields.Many2one("stock.barcode.lite.sunrise.order.import", string="Import", required=True, ondelete="cascade", copy=False, index=True)
    import_type = fields.Selection(related="import_id.import_type", string="Import Type", store=True, readonly=True, index=True)
    inbound_order_id = fields.Many2one(related="import_id.inbound_order_id", string="Inbound Order", store=True, readonly=True, index=True)
    outbound_order_id = fields.Many2one(related="import_id.outbound_order_id", string="Outbound Order", store=True, readonly=True, index=True)
    row_number = fields.Integer(string="Row Number", copy=False, index=True)
    state = fields.Selection([("success", "Success"), ("failed", "Failed")], string="State", default="failed", copy=False, index=True)
    error_msg = fields.Text(string="Error Message", copy=False)
    created_inbound_pallet_id = fields.Many2one("world.depot.inbound.order.product", string="Created Inbound Pallet", copy=False, index=True)
    created_inbound_detail_id = fields.Many2one("world.depot.inbound.order.products.pallet", string="Created Inbound Detail", copy=False, index=True)
    created_outbound_line_id = fields.Many2one("world.depot.outbound.order.product", string="Created Outbound Line", copy=False, index=True)
    product_id = fields.Many2one("product.product", string="Matched Product", copy=False, index=True)

    reference = fields.Char(string="Reference", copy=False, index=True)
    cntr_no = fields.Char(string="Container No", copy=False, index=True)
    inbound_cntr_no = fields.Char(string="Inbound Container No", copy=False, index=True)
    cwarehouseid = fields.Char(string="U8C Warehouse ID", copy=False, index=True)
    product = fields.Char(string="Product Code", copy=False, index=True)
    product_name = fields.Char(string="Product Name", copy=False)
    product_ean = fields.Char(string="Product EAN", copy=False, index=True)
    lot_name = fields.Char(string="Lot Name", copy=False, index=True)
    pallet_no = fields.Char(string="Pallet No", copy=False, index=True)
    package_barcode = fields.Char(string="Package Barcode", copy=False, index=True)
    cspaceid = fields.Char(string="Location Code", copy=False, index=True)
    box_qty = fields.Char(string="Box Qty", copy=False)
    box_in_qty = fields.Char(string="Box In Qty", copy=False)
    box_type = fields.Char(string="Box Type", copy=False, index=True)
    ninnum = fields.Char(string="Received Units", copy=False)
    castunitid = fields.Char(string="Assistant Unit", copy=False, index=True)
    u8_aux_uom_name = fields.Char(string="U8 Aux UOM Name", copy=False, index=True)
    u8_aux_qty = fields.Char(string="U8 Aux Qty", copy=False)
    u8_conversion_rate = fields.Char(string="U8 Conversion Rate", copy=False)
    vsourcebillcode = fields.Char(string="Source Bill Code", copy=False, index=True)
    vsourcerowno = fields.Char(string="Source Row No", copy=False, index=True)
    cprojectid = fields.Char(string="Contract No", copy=False, index=True)
    ndiscounttaxtype = fields.Char(string="Tax Deduction Type", copy=False, index=True)
    is_lot = fields.Char(string="Is Lot", copy=False, index=True)
    de_palletize = fields.Char(string="Depalletize", copy=False, index=True)
    m_date = fields.Char(string="Manufacture Date", copy=False)
    e_date = fields.Char(string="Expiration Date", copy=False)
    remark = fields.Text(string="Remark", copy=False)

    def action_retry_import(self):
        success_count = 0
        failed_count = 0
        import_records = self.mapped("import_id")
        for rec in self:
            if rec.state != "failed":
                raise UserError(_("Only failed import lines can be retried."))
            try:
                with rec.env.cr.savepoint():
                    rec.process_import_line()
                success_count += 1
            except Exception as error:
                rec.write({"state": "failed", "error_msg": str(error)})
                failed_count += 1
        import_records.refresh_result_counts()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Retry Import"),
                "message": _("Retry finished. Success: %(success)s, Failed: %(failed)s") % {"success": success_count, "failed": failed_count},
                "type": "success" if not failed_count else "warning",
                "sticky": False,
            },
        }

    def process_import_line(self):
        for rec in self:
            if rec.state == "success":
                raise UserError(_("Successful import lines cannot be retried."))
            if rec.import_type == "inbound":
                rec.process_inbound_line()
            elif rec.import_type == "outbound":
                rec.process_outbound_line()
            else:
                raise UserError(_("Unknown import type."))

    def process_inbound_line(self):
        inbound_order = self.inbound_order_id
        if not inbound_order:
            raise UserError(_("Inbound order is required."))
        if inbound_order.state != "new":
            raise UserError(_("Only new inbound orders can import products."))
        if inbound_order.project.name != "SUNRISE":
            raise UserError(_("Only SUNRISE inbound orders can import products."))

        reference = self.get_required_text("reference")
        cntr_no = self.get_required_text("cntr_no")
        cwarehouseid = self.get_required_text("cwarehouseid")
        vsourcebillcode = self.get_required_text("vsourcebillcode")
        self.ensure_order_header(inbound_order, {"reference": reference, "cntr_no": cntr_no, "cwarehouseid": cwarehouseid, "vsourcebillcode": vsourcebillcode})

        product_code = self.get_required_text("product")
        pallet_no = self.get_required_text("pallet_no")
        cprojectid = self.get_required_text("cprojectid")
        ndiscounttaxtype = self.get_required_text("ndiscounttaxtype")
        vsourcerowno = self.get_required_text("vsourcerowno")
        castunitid = self.get_required_text("castunitid")
        cspaceid = self.get_required_text("cspaceid")
        u8_aux_uom_name = self.get_required_text("u8_aux_uom_name")
        box_type, box_qty, box_in_qty, ninnum, u8_aux_qty, u8_conversion_rate = self.validate_box_values()
        is_lot, lot_name = self.validate_lot_values()
        product = self.get_sunrise_product_variant(product_code, box_type, box_in_qty, inbound_order.project, auto_create_variant=True)
        self.validate_product_tracking(product, is_lot, lot_name)

        pallet_model = self.env["world.depot.inbound.order.product"]
        detail_model = self.env["world.depot.inbound.order.products.pallet"]
        pallet_line = self.find_inbound_pallet_line(
            inbound_order,
            product_code,
            is_lot,
            lot_name,
            pallet_no,
        )
        if not pallet_line:
            reused_package = self.find_sunrise_reused_inbound_package(
                inbound_order,
                product_code,
                is_lot,
                lot_name,
                pallet_no,
            )
            pallet_line = pallet_model.create({
                "inbound_order_id": inbound_order.id,
                "creation_source": "import",
                "pallet_no": pallet_no,
                "pallets": 1,
                "package_id": reused_package.id if reused_package else False,
                "is_reused_package": bool(reused_package),
            })
        elif self.package_barcode and pallet_line.package_id and pallet_line.package_id.barcode != self.package_barcode:
            raise UserError(
                _('Row %s: package_barcode "%s" does not match the existing pallet package "%s".')
                % (self.row_number, self.package_barcode, pallet_line.package_id.barcode)
            )

        detail_line = detail_model.create({
            "inbound_order_product_id": pallet_line.id,
            "creation_source": "import",
            "product_id": product.id,
            "source_product_code": product_code,
            "product_ean": self.product_ean,
            "quantity": box_qty,
            "remark": self.remark,
            "cprojectid": cprojectid,
            "ndiscounttaxtype": ndiscounttaxtype,
            "vsourcebillcode": vsourcebillcode,
            "vsourcerowno": vsourcerowno,
            "cspaceid": cspaceid,
            "box_type": box_type,
            "box_qty": box_qty,
            "box_in_qty": box_in_qty,
            "ninnum": ninnum,
            "u8_aux_qty": u8_aux_qty,
            "u8_conversion_rate": u8_conversion_rate,
            "castunitid": castunitid,
            "u8_aux_uom_name": u8_aux_uom_name,
            "is_lot": is_lot,
            "lot_name": lot_name,
            "m_date": self.get_date_value("m_date"),
            "e_date": self.get_date_value("e_date"),
        })
        self.write({
            "state": "success",
            "error_msg": False,
            "product_id": product.id,
            "created_inbound_pallet_id": pallet_line.id,
            "created_inbound_detail_id": detail_line.id,
        })

    def process_outbound_line(self):
        outbound_order = self.outbound_order_id
        if not outbound_order:
            raise UserError(_("Outbound order is required."))
        if outbound_order.state != "new":
            raise UserError(_("Only new outbound orders can import products."))
        if outbound_order.project.name != "SUNRISE":
            raise UserError(_("Only SUNRISE outbound orders can import products."))

        reference = self.get_required_text("reference")
        cwarehouseid = self.get_required_text("cwarehouseid")
        vsourcebillcode = self.get_required_text("vsourcebillcode")
        self.ensure_order_header(outbound_order, {"reference": reference, "cwarehouseid": cwarehouseid, "vsourcebillcode": vsourcebillcode})

        product_code = self.get_required_text("product")
        pallet_no = self.get_required_text("pallet_no")
        de_palletize = self.get_optional_text("de_palletize").upper() or "Y"
        if de_palletize not in ("N", "Y"):
            raise UserError(_("Row %s: de_palletize must be N or Y.") % self.row_number)
        cprojectid = self.get_required_text("cprojectid")
        vsourcerowno = self.get_required_text("vsourcerowno")
        cspaceid = self.get_required_text("cspaceid")
        castunitid = self.get_required_text("castunitid")
        u8_aux_uom_name = self.get_required_text("u8_aux_uom_name")
        box_type, box_qty, box_in_qty, ninnum, u8_aux_qty, u8_conversion_rate = self.validate_box_values()
        is_lot, lot_name = self.validate_lot_values()
        product = self.get_sunrise_product_variant(product_code, box_type, box_in_qty, outbound_order.project)
        self.validate_product_tracking(product, is_lot, lot_name)
        existing_lines = self.env["world.depot.outbound.order.product"].sudo().search([
            ("outbound_order_id", "=", outbound_order.id),
        ])
        package = self.find_outbound_package(
            self.inbound_cntr_no,
            pallet_no,
            product,
            lot_name if is_lot == "Y" else "",
            outbound_order.project,
            box_qty,
            existing_lines,
            de_palletize,
        )
        existing_package_lines = existing_lines.filtered(lambda line: line.package_id == package)
        if existing_package_lines and any(line.de_palletize != de_palletize for line in existing_package_lines):
            raise UserError(_('Pallet "%s" cannot mix de_palletize=N and de_palletize=Y.') % package.name)
        pending_quantity = self.get_existing_outbound_quantity(
            existing_package_lines,
            product,
            lot_name if is_lot == "Y" else "",
        )
        self.check_package_stock(package, product, box_qty, lot_name if is_lot == "Y" else None, pending_quantity)

        outbound_line = self.env["world.depot.outbound.order.product"].create({
            "outbound_order_id": outbound_order.id,
            "creation_source": "import",
            "product_id": product.id,
            "source_product_code": product_code,
            "product_ean": self.product_ean,
            "pallet_no": pallet_no,
            "package_id": package.id,
            "de_palletize": de_palletize,
            "pallets": 1,
            "quantity": box_qty,
            "remark": self.remark,
            "cprojectid": cprojectid,
            "ndiscounttaxtype": self.ndiscounttaxtype,
            "vsourcebillcode": vsourcebillcode,
            "vsourcerowno": vsourcerowno,
            "cspaceid": cspaceid,
            "box_type": box_type,
            "box_qty": box_qty,
            "box_in_qty": box_in_qty,
            "ninnum": ninnum,
            "u8_aux_qty": u8_aux_qty,
            "u8_conversion_rate": u8_conversion_rate,
            "castunitid": castunitid,
            "u8_aux_uom_name": u8_aux_uom_name,
            "is_lot": is_lot,
            "lot_name": lot_name,
            "m_date": self.get_date_value("m_date"),
            "e_date": self.get_date_value("e_date"),
        })
        self.write({"state": "success", "error_msg": False, "product_id": product.id, "created_outbound_line_id": outbound_line.id})

    def ensure_order_header(self, order, values):
        write_values = {}
        for field_name, value in values.items():
            if field_name not in order._fields:
                continue
            current_value = self.import_id.cell_to_text(order[field_name])
            if current_value and current_value != value:
                raise UserError(_("Row %s: %s must be %s.") % (self.row_number, field_name, current_value))
            if not current_value and value:
                write_values[field_name] = value
        if write_values:
            order.write(write_values)

    def get_required_text(self, field_name):
        value = self.import_id.cell_to_text(self[field_name])
        if not value:
            raise UserError(_("Row %s: %s is required.") % (self.row_number, field_name))
        return value

    def get_optional_text(self, field_name):
        return self.import_id.cell_to_text(self[field_name])

    def get_positive_int(self, field_name):
        value = self.get_required_text(field_name)
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise UserError(_("Row %s: %s must be a positive integer.") % (self.row_number, field_name))
        if not math.isfinite(number) or number <= 0 or not number.is_integer():
            raise UserError(_("Row %s: %s must be a positive integer.") % (self.row_number, field_name))
        return int(number)

    def get_positive_float(self, field_name):
        value = self.get_required_text(field_name)
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise UserError(_("Row %s: %s must be a positive number.") % (self.row_number, field_name))
        if not math.isfinite(number) or number <= 0:
            raise UserError(_("Row %s: %s must be a positive number.") % (self.row_number, field_name))
        return number

    def get_date_value(self, field_name):
        value = self.get_optional_text(field_name)
        if not value:
            return False
        try:
            parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as error:
            raise UserError(_("Row %s: %s must be a valid date YYYY-MM-DD.") % (self.row_number, field_name)) from error
        if parsed_date.strftime("%Y-%m-%d") != value:
            raise UserError(_("Row %s: %s must be a valid date YYYY-MM-DD.") % (self.row_number, field_name))
        return value

    def validate_box_values(self):
        box_type = self.get_required_text("box_type").lower()
        if box_type not in ("full", "partial"):
            raise UserError(_("Row %s: box_type must be full or partial.") % self.row_number)
        box_qty = self.get_positive_int("box_qty")
        box_in_qty = self.get_positive_float("box_in_qty")
        ninnum = self.get_positive_float("ninnum")
        u8_aux_qty = self.get_positive_float("u8_aux_qty")
        u8_conversion_rate = self.get_positive_float("u8_conversion_rate")
        if not math.isclose(ninnum, box_qty * box_in_qty, rel_tol=1e-9, abs_tol=1e-6):
            raise UserError(_("Row %s: ninnum must equal box_qty * box_in_qty.") % self.row_number)
        if box_type == "full" and not math.isclose(box_in_qty, u8_conversion_rate, rel_tol=1e-9, abs_tol=1e-6):
            raise UserError(_("Row %s: box_in_qty must equal u8_conversion_rate when box_type is full.") % self.row_number)
        if box_type == "partial" and math.isclose(
                box_in_qty,
                u8_conversion_rate,
                rel_tol=1e-9,
                abs_tol=1e-6,
        ):
            raise UserError(
                _("Row %s: box_in_qty must not equal u8_conversion_rate when box_type is partial.")
                % self.row_number
            )
        return box_type, box_qty, box_in_qty, ninnum, u8_aux_qty, u8_conversion_rate

    def validate_lot_values(self):
        is_lot = self.get_required_text("is_lot").upper()
        if is_lot not in ("Y", "N"):
            raise UserError(_("Row %s: is_lot must be Y or N.") % self.row_number)
        lot_name = self.get_optional_text("lot_name")
        if is_lot == "Y" and not lot_name:
            raise UserError(_("Row %s: lot_name is required when is_lot is Y.") % self.row_number)
        return is_lot, lot_name

    def validate_product_tracking(self, product, is_lot, lot_name):
        if product.tracking == "serial":
            raise UserError(_('Row %s: serial-tracked product "%s" is not supported.') % (self.row_number, product.display_name))
        if product.tracking == "lot" and is_lot != "Y":
            raise UserError(_('Row %s: product "%s" enables lot tracking, so is_lot must be Y.') % (self.row_number, product.display_name))
        if product.tracking != "lot" and is_lot != "N":
            raise UserError(_('Row %s: is_lot must be N for non-lot-tracked product "%s".') % (self.row_number, product.display_name))
        if is_lot == "Y" and not lot_name:
            raise UserError(_('Row %s: lot_name is required for product "%s".') % (self.row_number, product.display_name))

    def get_sunrise_pallet_group_key(self, product_code, is_lot, lot_name, pallet_no):
        return (
            (product_code or "").strip(),
            (lot_name or "").strip() if is_lot == "Y" else "",
            (pallet_no or "").strip(),
        )

    def find_inbound_pallet_line(self, inbound_order, product_code, is_lot, lot_name, pallet_no):
        pallet_model = self.env["world.depot.inbound.order.product"]
        expected_key = self.get_sunrise_pallet_group_key(product_code, is_lot, lot_name, pallet_no)
        candidates = pallet_model.sudo().search([
            ("inbound_order_id", "=", inbound_order.id),
            ("pallet_no", "=", expected_key[2]),
        ])
        matched_ids = []
        for candidate in candidates:
            detail_keys = {
                self.get_sunrise_pallet_group_key(
                    detail.source_product_code or detail.product_id.barcode,
                    detail.is_lot,
                    detail.lot_name,
                    candidate.pallet_no,
                )
                for detail in candidate.inbound_order_product_pallet_ids
            }
            if detail_keys == {expected_key}:
                matched_ids.append(candidate.id)
        if len(matched_ids) > 1:
            raise UserError(
                _("Row %s: multiple physical pallets match product \"%s\", lot \"%s\", and pallet_no \"%s\" in this inbound order.")
                % (self.row_number, expected_key[0], expected_key[1], expected_key[2])
            )
        return pallet_model.browse(matched_ids[0]) if matched_ids else pallet_model

    def find_sunrise_reused_inbound_package(self, inbound_order, product_code, is_lot, lot_name, pallet_no):
        pallet_model = self.env["world.depot.inbound.order.product"]
        package_model = self.env["stock.quant.package"]
        expected_key = self.get_sunrise_pallet_group_key(product_code, is_lot, lot_name, pallet_no)
        candidates = pallet_model.sudo().search([
            ("inbound_order_id", "!=", inbound_order.id),
            ("inbound_order_id.project", "=", inbound_order.project.id),
            ("inbound_order_id.state", "=", "confirm"),
            ("pallet_no", "=", expected_key[2]),
            ("package_id", "!=", False),
        ])
        package_ids = set()
        for candidate in candidates:
            detail_keys = {
                self.get_sunrise_pallet_group_key(
                    detail.source_product_code or detail.product_id.barcode,
                    detail.is_lot,
                    detail.lot_name,
                    candidate.pallet_no,
                )
                for detail in candidate.inbound_order_product_pallet_ids
            }
            if detail_keys != {expected_key}:
                continue
            if self.package_barcode and candidate.package_id.barcode != self.package_barcode:
                continue
            package_ids.add(candidate.package_id.id)

        if not package_ids:
            if self.package_barcode:
                raise UserError(
                    _('Row %s: package_barcode "%s" does not match a confirmed inbound pallet for this project.')
                    % (self.row_number, self.package_barcode)
                )
            return package_model
        if len(package_ids) > 1:
            raise UserError(
                _('Row %s: multiple existing packages match product "%s", lot "%s", and pallet_no "%s". Please fill package_barcode.')
                % (self.row_number, expected_key[0], expected_key[1], expected_key[2])
            )
        return package_model.browse(next(iter(package_ids)))

    def get_sunrise_package_value_name(self, box_type, box_in_qty):
        if box_type == "full":
            return "Standard Packaging"
        return "Non standard package%s" % box_in_qty

    def get_sunrise_variant_default_code(self, product_code, box_type, box_in_qty):
        if box_type == "full":
            return "%s-FULL-%s" % (product_code, box_in_qty)
        return "%s-PARTIAL-%s" % (product_code, box_in_qty)

    def get_sunrise_package_variants(self, variants, value_name):
        return variants.filtered(lambda variant: value_name in variant.product_template_attribute_value_ids.mapped("name"))

    def get_sunrise_product_variant(self, product_code, box_type, box_in_qty, project, auto_create_variant=False):
        product_model = self.env["product.product"]
        standard_products = product_model.sudo().search([("barcode", "=", product_code)])
        if project.category:
            standard_products = standard_products.filtered(lambda product: product.categ_id == project.category)
        if not standard_products:
            raise UserError(_('Row %s: standard carton product with barcode "%s" was not found.') % (self.row_number, product_code))
        if len(standard_products) > 1:
            raise UserError(_('Row %s: barcode "%s" matched multiple standard carton products.') % (self.row_number, product_code))
        standard_product = product_model.browse(standard_products[:1].id)
        if box_type == "full":
            return standard_product

        template = standard_product.product_tmpl_id
        target_value_name = self.get_sunrise_package_value_name(box_type, box_in_qty)
        variants = product_model.sudo().search([("product_tmpl_id", "=", template.id)])
        matched_variants = self.get_sunrise_package_variants(variants, target_value_name)
        if not matched_variants and auto_create_variant:
            self.ensure_sunrise_package_value_on_template(template, target_value_name)
            variants = product_model.sudo().search([("product_tmpl_id", "=", template.id)])
            matched_variants = self.get_sunrise_package_variants(variants, target_value_name)
        if not matched_variants:
            raise UserError(_('Row %s: product barcode "%s" has no partial variant with package value "%s".') % (self.row_number, product_code, target_value_name))
        if len(matched_variants) > 1:
            raise UserError(_('Row %s: product barcode "%s" has multiple partial variants with package value "%s".') % (self.row_number, product_code, target_value_name))
        product = product_model.browse(matched_variants[:1].id)
        if auto_create_variant and not product.default_code:
            product.write({"default_code": self.get_sunrise_variant_default_code(product_code, box_type, box_in_qty), "barcode": self.get_sunrise_variant_default_code(product_code, box_type, box_in_qty)})
        return product

    def ensure_sunrise_package_value_on_template(self, template, value_name):
        attribute_model = self.env["product.attribute"]
        value_model = self.env["product.attribute.value"]
        line_model = self.env["product.template.attribute.line"]
        attribute = attribute_model.sudo().search([("name", "=", "Packaging Specifications")], limit=1)
        if not attribute:
            raise UserError(_('No attribute named "Packaging Specifications" was found.'))
        value = value_model.sudo().search([("attribute_id", "=", attribute.id), ("name", "=", value_name)], limit=1)
        if not value:
            value = value_model.create({"attribute_id": attribute.id, "name": value_name})
        line = line_model.sudo().search([("product_tmpl_id", "=", template.id), ("attribute_id", "=", attribute.id)], limit=1)
        if line:
            normal_line = line_model.browse(line.id)
            if value.id not in normal_line.value_ids.ids:
                normal_line.write({"value_ids": [(4, value.id)]})
        else:
            line_model.create({"product_tmpl_id": template.id, "attribute_id": attribute.id, "value_ids": [(6, 0, [value.id])]})

    def find_outbound_package(self, inbound_cntr_no, pallet_no, product, lot_name, project, required_quantity, existing_lines, de_palletize):
        inbound_pallet_model = self.env["world.depot.inbound.order.product"]
        package_model = self.env["stock.quant.package"]
        quant_model = self.env["stock.quant"]
        lot_model = self.env["stock.lot"]

        inbound_pallets = inbound_pallet_model.sudo().search([
            ("pallet_no", "=", pallet_no),
            ("package_id", "!=", False),
            ("inbound_order_id.project", "=", project.id),
            ("inbound_order_id.state", "!=", "cancel"),
        ])
        if not inbound_pallets:
            raise UserError(_('Row %s: pallet_no "%s" has no inbound pallet mapping for this project.') % (self.row_number, pallet_no))

        packages = inbound_pallets.mapped("package_id")
        if not packages:
            raise UserError(_('Row %s: pallet_no "%s" has no stock package.') % (self.row_number, pallet_no))

        quant_domain = [("package_id", "in", packages.ids), ("product_id", "=", product.id), ("location_id.usage", "=", "internal")]
        if lot_name:
            lot = lot_model.sudo().search([("product_id", "=", product.id), ("name", "=", lot_name)], limit=1)
            if not lot:
                raise UserError(_('Row %s: lot_name "%s" has no stock for this product.') % (self.row_number, lot_name))
            quant_domain.append(("lot_id", "=", lot.id))
        quants = quant_model.sudo().search(quant_domain)
        available_by_package = {}
        for quant in quants:
            available_by_package.setdefault(quant.package_id.id, 0.0)
            available_by_package[quant.package_id.id] += (quant.quantity or 0.0) - (quant.reserved_quantity or 0.0)
        candidate_packages = packages.filtered(lambda package: available_by_package.get(package.id, 0.0) > 0)
        if not candidate_packages:
            raise UserError(_('Row %s: pallet_no "%s" has no available stock for product "%s" and lot "%s".') % (self.row_number, pallet_no, product.display_name, lot_name or ""))

        ordered_packages = package_model.sudo().search(
            [("id", "in", candidate_packages.ids)],
            order="create_date asc, id asc",
        )
        for package in ordered_packages:
            existing_package_lines = existing_lines.filtered(lambda line: line.package_id == package)
            if existing_package_lines and any(line.de_palletize != de_palletize for line in existing_package_lines):
                continue
            pending_quantity = self.get_existing_outbound_quantity(
                existing_package_lines,
                product,
                lot_name,
            )
            if available_by_package.get(package.id, 0.0) >= required_quantity + pending_quantity:
                return package_model.browse(package.id)

        raise UserError(
            _('Row %s: no single stock package has enough product "%s" for pallet_no "%s" and lot "%s".')
            % (self.row_number, product.display_name, pallet_no, lot_name or "")
        )

    def get_existing_outbound_quantity(self, existing_lines, product, lot_name):
        matching_lines = existing_lines.filtered(lambda line: line.product_id == product and (line.lot_name or "") == (lot_name or ""))
        return sum(matching_lines.mapped("quantity"))

    def check_package_stock(self, package, product, quantity, lot_name=None, pending_quantity=0.0):
        quant_model = self.env["stock.quant"]
        lot_model = self.env["stock.lot"]
        quant_domain = [("package_id", "=", package.id), ("product_id", "=", product.id), ("location_id.usage", "=", "internal")]
        if lot_name:
            lot = lot_model.sudo().search([("product_id", "=", product.id), ("name", "=", lot_name)], limit=1)
            if not lot:
                raise UserError(_('Row %s: lot "%s" has no stock for product "%s".') % (self.row_number, lot_name, product.display_name))
            quant_domain.append(("lot_id", "=", lot.id))
        quants = quant_model.sudo().search(quant_domain)
        available_quantity = sum(quants.mapped("quantity")) - sum(quants.mapped("reserved_quantity"))
        required_quantity = quantity + pending_quantity
        if available_quantity < required_quantity:
            raise UserError(_('Row %s: insufficient stock for product "%s" on pallet "%s": need %s, available %s.') % (self.row_number, product.display_name, package.name, required_quantity, available_quantity))
