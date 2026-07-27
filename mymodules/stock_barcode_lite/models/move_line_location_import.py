# -*- coding: utf-8 -*-

import base64
import binascii
import math
import os
from io import BytesIO

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import xlrd
except ImportError:
    xlrd = None


class MoveLineLocationImport(models.Model):
    _name = "move.line.location.import"
    _description = "Move Line Location Import"
    _order = "id desc"

    name = fields.Char(string="Name", required=True, default="Move Line Location Import", copy=False, index=True)
    file = fields.Binary(string="Excel File", required=True, copy=False)
    filename = fields.Char(string="Filename", copy=False)
    picking_id = fields.Many2one("stock.picking", string="Picking", readonly=True, copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("validated", "Validated"), ("failed", "Failed"), ("imported", "Imported")], string="State", default="draft", required=True, copy=False, index=True)
    total_count = fields.Integer(string="Total Count", readonly=True, copy=False)
    valid_count = fields.Integer(string="Valid Count", readonly=True, copy=False)
    error_count = fields.Integer(string="Error Count", readonly=True, copy=False)
    validation_datetime = fields.Datetime(string="Validation Datetime", readonly=True, copy=False)
    import_datetime = fields.Datetime(string="Import Datetime", readonly=True, copy=False)
    message = fields.Text(string="Message", readonly=True, copy=False)
    import_lines = fields.One2many("move.line.location.import.line", "import_id", string="Import Lines", readonly=True, copy=False)

    def cell_to_text(self, value):
        if value is None:
            return ""
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    def get_header_map(self, header_row):
        supported_fields = {
            "id",
            "product_id",
            "lot_id",
            "quantity",
            "result_package_id",
            "location_dest_id",
            "product_uom_id",
            "is_location_updated",
        }
        header_map = {}
        for index, value in enumerate(header_row):
            header = self.cell_to_text(value).strip().lower()
            if header not in supported_fields and "(" in header and ")" in header:
                header = header.rsplit("(", 1)[1].split(")", 1)[0].strip()
            if header in supported_fields and header not in header_map:
                header_map[header] = index

        required_headers = {
            "id",
            "product_id",
            "lot_id",
            "quantity",
            "result_package_id",
            "location_dest_id",
            "product_uom_id",
        }
        missing_headers = sorted(required_headers - set(header_map))
        if missing_headers:
            raise UserError(_("Missing required Excel headers: %s") % ", ".join(missing_headers))
        return header_map

    def read_excel_rows(self):
        self.ensure_one()
        try:
            file_content = base64.b64decode(self.file)
        except (binascii.Error, TypeError, ValueError) as error:
            raise UserError(_("Cannot read Excel file: %s") % str(error))

        extension = os.path.splitext(self.filename or "")[1].lower()
        if extension not in (".xlsx", ".xls"):
            if file_content.startswith(b"PK"):
                extension = ".xlsx"
            elif file_content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
                extension = ".xls"
            else:
                raise UserError(_("Only .xlsx and .xls files are supported."))

        def append_row(rows, header_map, row_values, row_number):
            if not any(self.cell_to_text(value) for value in row_values):
                return
            row_data = {}
            for header, index in header_map.items():
                row_data[header] = self.cell_to_text(row_values[index]) if index < len(row_values) else ""
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

    def action_validate_file(self):
        line_model = self.env["move.line.location.import.line"]
        notifications = []
        for rec in self:
            if rec.state == "imported":
                raise UserError(_("Imported records cannot be validated again."))
            if not rec.file:
                raise UserError(_("Please upload an Excel file."))

            if not rec.import_lines:
                try:
                    rows = rec.read_excel_rows()
                except UserError as error:
                    rec.write({
                        "state": "failed",
                        "message": str(error),
                        "total_count": 0,
                        "valid_count": 0,
                        "error_count": 0,
                        "validation_datetime": fields.Datetime.now(),
                    })
                    notifications.append(str(error))
                    continue
                if not rows:
                    message = _("The Excel file has no data rows.")
                    rec.write({
                        "state": "failed",
                        "message": message,
                        "total_count": 0,
                        "valid_count": 0,
                        "error_count": 0,
                        "validation_datetime": fields.Datetime.now(),
                    })
                    notifications.append(message)
                    continue

                for row_number, row_data in rows:
                    line_model.create({
                        "name": "%s Row %s" % (rec.name, row_number),
                        "import_id": rec.id,
                        "row_number": row_number,
                        "source_move_line_external_id": row_data.get("id", ""),
                        "source_product_name": row_data.get("product_id", ""),
                        "source_lot_name": row_data.get("lot_id", ""),
                        "source_quantity_text": row_data.get("quantity", ""),
                        "source_package_name": row_data.get("result_package_id", ""),
                        "source_location_name": row_data.get("location_dest_id", ""),
                        "source_uom_name": row_data.get("product_uom_id", ""),
                        "source_is_location_updated": row_data.get("is_location_updated", ""),
                    })

            rec.validate_import_lines(check_snapshot=False)
            notifications.append(rec.message)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Move Line Location Import"),
                "message": "\n".join(notifications),
                "type": "success" if all(rec.state == "validated" for rec in self) else "warning",
                "sticky": False,
            },
        }

    def validate_import_lines(self, check_snapshot=False):
        for rec in self:
            if not rec.import_lines:
                rec.write({
                    "state": "failed",
                    "picking_id": False,
                    "total_count": 0,
                    "valid_count": 0,
                    "error_count": 0,
                    "validation_datetime": fields.Datetime.now(),
                    "message": _("The Excel file has no data rows."),
                })
                continue

            for line in rec.import_lines:
                line.validate_import_line(check_snapshot=check_snapshot)

            seen_move_line_ids = {}
            for line in rec.import_lines.sorted("row_number"):
                source_id = (line.source_move_line_external_id or "").strip()
                if not source_id:
                    continue
                if source_id not in seen_move_line_ids:
                    seen_move_line_ids[source_id] = line
                    continue
                first_line = seen_move_line_ids[source_id]
                detail = _("[id] Duplicate Excel move line ID. First found at row %s.") % first_line.row_number
                error_fields = set(filter(None, (line.error_field_names or "").split(",")))
                error_fields.add("id")
                line.write({
                    "state": "error",
                    "error_field_names": ",".join(sorted(error_fields)),
                    "validation_details": "\n".join(filter(None, [line.validation_details, detail])),
                    "validation_log": "\n".join(filter(None, [line.validation_log, "%s %s" % (fields.Datetime.to_string(fields.Datetime.now()), detail)])),
                })

            matched_lines = rec.import_lines.filtered(lambda line: line.matched_picking_id)
            picking_ids = matched_lines.mapped("matched_picking_id")
            if len(picking_ids) != 1:
                for line in matched_lines:
                    detail = _("[picking_id] Excel rows must belong to one picking. Current picking: %s.") % line.matched_picking_id.name
                    error_fields = set(filter(None, (line.error_field_names or "").split(",")))
                    error_fields.add("picking_id")
                    line.write({
                        "state": "error",
                        "error_field_names": ",".join(sorted(error_fields)),
                        "validation_details": "\n".join(filter(None, [line.validation_details, detail])),
                        "validation_log": "\n".join(filter(None, [line.validation_log, "%s %s" % (fields.Datetime.to_string(fields.Datetime.now()), detail)])),
                    })
                rec.write({"picking_id": False})
            else:
                rec.write({"picking_id": picking_ids.id})

            valid_count = len(rec.import_lines.filtered(lambda line: line.state == "valid"))
            total_count = len(rec.import_lines)
            error_count = total_count - valid_count
            state = "validated" if valid_count == total_count else "failed"
            rec.write({
                "state": state,
                "total_count": total_count,
                "valid_count": valid_count,
                "error_count": error_count,
                "validation_datetime": fields.Datetime.now(),
                "message": _("Validation finished. Valid: %(valid)s, Error: %(error)s.") % {
                    "valid": valid_count,
                    "error": error_count,
                },
            })
        return True

    def action_confirm_import(self):
        notifications = []
        for rec in self:
            if rec.state != "validated":
                raise UserError(_("Only validated import records can be confirmed."))

            move_line_ids = sorted(rec.import_lines.mapped("move_line_id").ids)
            if not move_line_ids:
                raise UserError(_("No stock move lines were found for this import."))
            self.env.cr.execute(
                "SELECT id FROM stock_move_line WHERE id IN %s FOR UPDATE",
                [tuple(move_line_ids)],
            )

            rec.validate_import_lines(check_snapshot=True)
            if rec.state != "validated":
                notifications.append(_("Import %s was not written because stock move lines changed after validation.") % rec.name)
                continue

            import_datetime = fields.Datetime.now()
            for line in rec.import_lines:
                move_line = self.env["stock.move.line"].browse(line.move_line_id.id)
                move_line.write({
                    "location_dest_id": line.target_location_id.id,
                    "is_location_updated": True,
                    "location_updated_by_id": self.env.user.id,
                    "location_updated_datetime": import_datetime,
                })
                import_log = _("Imported target location %s.") % line.target_location_id.complete_name
                line.write({
                    "state": "imported",
                    "validation_log": "\n".join(filter(None, [line.validation_log, "%s %s" % (fields.Datetime.to_string(import_datetime), import_log)])),
                })

            rec.write({
                "state": "imported",
                "import_datetime": import_datetime,
                "message": _("Import completed. Updated %s stock move lines.") % len(rec.import_lines),
            })
            notifications.append(rec.message)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Move Line Location Import"),
                "message": "\n".join(notifications),
                "type": "success" if all(rec.state == "imported" for rec in self) else "warning",
                "sticky": False,
            },
        }


class MoveLineLocationImportLine(models.Model):
    _name = "move.line.location.import.line"
    _description = "Move Line Location Import Line"
    _order = "id desc"

    name = fields.Char(string="Name", required=True, copy=False, index=True)
    import_id = fields.Many2one("move.line.location.import", string="Import", required=True, ondelete="cascade", copy=False, index=True)
    row_number = fields.Integer(string="Row Number", required=True, copy=False, index=True)
    state = fields.Selection([("pending", "Pending"), ("valid", "Valid"), ("error", "Error"), ("stale", "Stale"), ("imported", "Imported")], string="State", default="pending", required=True, copy=False, index=True)
    source_move_line_external_id = fields.Char(string="Excel Move Line ID", copy=False, index=True)
    source_product_name = fields.Char(string="Excel Product", copy=False)
    source_lot_name = fields.Char(string="Excel Lot", copy=False, index=True)
    source_quantity_text = fields.Char(string="Excel Quantity", copy=False)
    source_package_name = fields.Char(string="Excel Pallet", copy=False, index=True)
    source_location_name = fields.Char(string="Excel Target Location", copy=False, index=True)
    source_uom_name = fields.Char(string="Excel UoM", copy=False)
    source_is_location_updated = fields.Char(string="Excel Location Updated", copy=False)
    move_line_id = fields.Many2one("stock.move.line", string="Stock Move Line", readonly=True, copy=False, index=True)
    matched_picking_id = fields.Many2one("stock.picking", string="Matched Picking", readonly=True, copy=False, index=True)
    target_location_id = fields.Many2one("stock.location", string="Target Location", readonly=True, copy=False, index=True)
    current_product_name = fields.Char(string="Current Product", readonly=True, copy=False)
    current_lot_name = fields.Char(string="Current Lot", readonly=True, copy=False, index=True)
    current_quantity = fields.Float(string="Current Quantity", readonly=True, copy=False)
    current_package_name = fields.Char(string="Current Pallet", readonly=True, copy=False, index=True)
    current_uom_name = fields.Char(string="Current UoM", readonly=True, copy=False)
    current_location_name = fields.Char(string="Current Target Location", readonly=True, copy=False, index=True)
    snapshot_write_datetime = fields.Datetime(string="Move Line Write Datetime", readonly=True, copy=False)
    error_field_names = fields.Char(string="Error Fields", readonly=True, copy=False, index=True)
    validation_details = fields.Text(string="Validation Details", readonly=True, copy=False)
    validation_log = fields.Text(string="Validation Log", readonly=True, copy=False)

    def get_move_line_from_source_id(self, source_id):
        move_line_model = self.env["stock.move.line"]
        external_id_model = self.env["ir.model.data"]
        source_id = (source_id or "").strip()
        if not source_id:
            return move_line_model
        if source_id.isdigit():
            return move_line_model.sudo().search([("id", "=", int(source_id))], limit=2)
        if "." not in source_id:
            return move_line_model
        module, name = source_id.split(".", 1)
        external_id = external_id_model.sudo().search([
            ("module", "=", module),
            ("name", "=", name),
            ("model", "=", "stock.move.line"),
        ], limit=2)
        if len(external_id) != 1:
            return move_line_model
        return move_line_model.sudo().search([("id", "=", external_id.res_id)], limit=2)

    def get_quantity_from_text(self, value):
        if isinstance(value, bool):
            return False
        text = (value or "").strip().replace(",", "")
        if not text:
            return False
        try:
            quantity = float(text)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(quantity):
            return False
        return quantity

    def validate_import_line(self, check_snapshot=False):
        location_model = self.env["stock.location"]
        for rec in self:
            errors = []
            notes = []
            stale = False
            move_line = rec.get_move_line_from_source_id(rec.source_move_line_external_id)
            values = {
                "move_line_id": False,
                "matched_picking_id": False,
                "target_location_id": False,
                "current_product_name": False,
                "current_lot_name": False,
                "current_quantity": 0.0,
                "current_package_name": False,
                "current_uom_name": False,
                "current_location_name": False,
                "snapshot_write_datetime": False,
            }

            if not rec.source_move_line_external_id:
                errors.append(_("[id] Excel move line ID is required."))
            elif len(move_line) != 1:
                errors.append(_("[id] Stock move line \"%s\" was not found.") % rec.source_move_line_external_id)
            else:
                package = move_line.result_package_id
                current_package_name = package.name or package.barcode or ""
                values.update({
                    "move_line_id": move_line.id,
                    "matched_picking_id": move_line.picking_id.id,
                    "current_product_name": move_line.product_id.display_name,
                    "current_lot_name": move_line.lot_id.name or "",
                    "current_quantity": move_line.quantity,
                    "current_package_name": current_package_name,
                    "current_uom_name": move_line.product_uom_id.name or "",
                    "current_location_name": move_line.location_dest_id.complete_name or "",
                    "snapshot_write_datetime": move_line.write_date,
                })

                picking = move_line.picking_id
                if not picking or picking.picking_type_id.code != "incoming":
                    errors.append(_("[picking_id] Stock move line does not belong to an incoming picking."))
                elif not picking.inbound_order_id or picking.inbound_order_id.project.name != "SUNRISE":
                    errors.append(_("[picking_id] Picking %s is not a Sunrise inbound picking.") % picking.name)
                elif picking.state in ("done", "cancel"):
                    errors.append(_("[picking_id] Picking %s is already %s.") % (picking.name, picking.state))

                if check_snapshot and rec.snapshot_write_datetime and move_line.write_date != rec.snapshot_write_datetime:
                    stale = True
                    errors.append(_("[write_date] Stock move line changed after validation. Previous: %s; Current: %s.") % (
                        fields.Datetime.to_string(rec.snapshot_write_datetime),
                        fields.Datetime.to_string(move_line.write_date),
                    ))

                if not rec.source_product_name:
                    errors.append(_("[product_id] Excel product is required."))
                elif rec.source_product_name != move_line.product_id.display_name:
                    errors.append(_("[product_id] Excel: %s; Current: %s.") % (
                        rec.source_product_name,
                        move_line.product_id.display_name,
                    ))

                current_lot_name = move_line.lot_id.name or ""
                if rec.source_lot_name != current_lot_name:
                    errors.append(_("[lot_id] Excel: %s; Current: %s.") % (rec.source_lot_name or "-", current_lot_name or "-"))

                if not rec.source_package_name:
                    errors.append(_("[result_package_id] Excel pallet is required."))
                elif not package:
                    errors.append(_("[result_package_id] Stock move line has no pallet."))
                elif rec.source_package_name not in {package.name or "", package.barcode or "", package.display_name or ""}:
                    package_names = {package.name or "", package.barcode or ""}
                    if rec.source_package_name.endswith("0") and rec.source_package_name[-2:-1].isalpha() and rec.source_package_name[:-1] in package_names:
                        notes.append(_("[result_package_id] Excel: %s; Current: %s. Legacy trailing-zero package name accepted.") % (
                            rec.source_package_name,
                            current_package_name or "-",
                        ))
                    else:
                        errors.append(_("[result_package_id] Excel: %s; Current: %s.") % (
                            rec.source_package_name,
                            current_package_name or "-",
                        ))

                quantity = rec.get_quantity_from_text(rec.source_quantity_text)
                rounding = move_line.product_uom_id.rounding or move_line.product_id.uom_id.rounding
                if quantity is False:
                    errors.append(_("[quantity] Excel quantity \"%s\" is invalid.") % rec.source_quantity_text)
                elif float_compare(quantity, move_line.quantity, precision_rounding=rounding) != 0:
                    errors.append(_("[quantity] Excel: %s; Current: %s.") % (rec.source_quantity_text, move_line.quantity))

                current_uom_name = move_line.product_uom_id.name or ""
                if not rec.source_uom_name:
                    errors.append(_("[product_uom_id] Excel UoM is required."))
                elif rec.source_uom_name != current_uom_name:
                    errors.append(_("[product_uom_id] Excel: %s; Current: %s.") % (
                        rec.source_uom_name,
                        current_uom_name,
                    ))

            location_name = rec.source_location_name or "SPN/Stock/LOODS11/sunrise_suspicious_location"
            locations = location_model.sudo().search([
                ("complete_name", "=", location_name),
                ("usage", "=", "internal"),
                ("active", "=", True),
            ], limit=2)
            if len(locations) != 1:
                errors.append(_("[location_dest_id] Internal location \"%s\" was not found or is not unique.") % location_name)
            else:
                values["target_location_id"] = locations.id

            error_field_names = []
            for error in errors:
                if error.startswith("[") and "]" in error:
                    error_field_names.append(error.split("]", 1)[0][1:])
            state = "stale" if stale else "error" if errors else "valid"
            row_header = _("Row %(row)s | %(product)s") % {
                "row": rec.row_number,
                "product": rec.source_product_name or "-",
            }
            validation_details = "\n".join([row_header] + errors + notes) if errors else "\n".join([row_header, _("Validation passed.")] + notes)
            log_message = _("Validation failed: %s") % "; ".join(error_field_names) if errors else _("Validation passed with note: %s") % " ".join(notes) if notes else _("Validation passed.")
            values.update({
                "state": state,
                "error_field_names": ",".join(sorted(set(error_field_names))),
                "validation_details": validation_details,
                "validation_log": "\n".join(filter(None, [rec.validation_log, "%s %s" % (fields.Datetime.to_string(fields.Datetime.now()), log_message)])),
            })
            rec.write(values)
        return True
