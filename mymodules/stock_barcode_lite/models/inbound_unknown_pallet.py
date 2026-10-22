# -*- coding: utf-8 -*-

import base64
import io
from collections import defaultdict
import re

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"

    project_pallet_structure_mode = fields.Selection(related="project.pallet_structure_mode", string="Pallet Structure Mode", readonly=True)
    actual_pallet_lines = fields.One2many("world.depot.inbound.order.actual.pallet", "inbound_order_id", string="Actual Pallets", copy=False)
    actual_pallet_structure_validated = fields.Boolean(string="Actual Pallet Structure Validated", default=False, readonly=True, copy=False)
    actual_pallet_difference_confirmed = fields.Boolean(string="Actual Pallet Difference Confirmed", default=False, readonly=True, copy=False)
    actual_pallet_difference_confirmed_by_id = fields.Many2one("res.users", string="Actual Pallet Difference Confirmed By", readonly=True, copy=False, index=True)
    actual_pallet_difference_confirmed_datetime = fields.Datetime(string="Actual Pallet Difference Confirmed At", readonly=True, copy=False)
    actual_pallet_structure_locked = fields.Boolean(compute="_compute_actual_pallet_structure_locked", store=True, readonly=True, copy=False)
    actual_pallet_difference_lines = fields.One2many("world.depot.inbound.order.actual.pallet.difference", "inbound_order_id", string="Actual Pallet Difference", readonly=True, copy=False)

    @api.depends("state", "stock_picking_id", "actual_pallet_difference_confirmed")
    def _compute_actual_pallet_structure_locked(self):
        for rec in self:
            rec.actual_pallet_structure_locked = rec.state != "new" or bool(rec.stock_picking_id) or rec.actual_pallet_difference_confirmed

    def action_open_actual_pallet_create_wizard(self):
        for rec in self:
            rec.check_unknown_pallet_structure_available()
            return {
                "type": "ir.actions.act_window",
                "name": _("Create Actual Pallets"),
                "res_model": "inbound.actual.pallet.create.wizard",
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "new",
                "context": {"default_inbound_order_id": rec.id},
            }
        return False

    def check_unknown_pallet_structure_available(self):
        picking_model = self.env["stock.picking"]
        for rec in self:
            if rec.project.pallet_structure_mode != "unknown":
                raise UserError(_("Actual pallet binding is available only for projects with Unknown Pallet Structure."))
            if rec.project.package_generation_mode != "inbound":
                raise UserError(_("Unknown Pallet Structure requires Package Generation Mode to be Inbound."))
            if rec.state != "new":
                raise UserError(_("Actual pallets can only be maintained before the inbound order is confirmed."))
            if rec.actual_pallet_difference_confirmed:
                raise UserError(_("Actual pallets cannot be changed after the pallet difference is confirmed."))
            picking = picking_model.sudo().search([("inbound_order_id", "=", rec.id), ("state", "!=", "cancel")], limit=1)
            if picking:
                raise UserError(_("Actual pallets cannot be maintained after a receipt exists."))
        return True

    def check_actual_pallet_structure_editable(self):
        picking_model = self.env["stock.picking"]
        for rec in self:
            if rec.project.pallet_structure_mode != "unknown":
                continue
            if rec.actual_pallet_difference_confirmed:
                raise UserError(_("Actual pallets cannot be changed after the pallet difference is confirmed."))
            if rec.state != "new":
                raise UserError(_("Actual pallets can only be maintained before the inbound order is confirmed."))
            if picking_model.sudo().search([("inbound_order_id", "=", rec.id), ("state", "!=", "cancel")], limit=1):
                raise UserError(_("Actual pallets cannot be maintained after a receipt exists."))
        return True

    def clear_actual_pallet_structure_validation(self):
        for rec in self:
            if rec.project.pallet_structure_mode != "unknown":
                continue
            if rec.actual_pallet_difference_confirmed:
                raise UserError(_("Actual pallets cannot be changed after the pallet difference is confirmed."))
            rec.write({"actual_pallet_structure_validated": False})
        return True

    def check_actual_pallet_structure_validated(self):
        for rec in self:
            if rec.project.pallet_structure_mode != "unknown":
                continue
            if rec.actual_pallet_structure_validated:
                continue
            if rec.actual_pallet_difference_lines:
                raise UserError(_("Actual pallet differences must be confirmed before confirming the inbound order or creating the receipt."))
            raise UserError(_("Validate the actual pallet structure before confirming the inbound order or creating the receipt."))
        return True

    def action_create_actual_pallets(self, pallet_count):
        actual_pallet_model = self.env["world.depot.inbound.order.actual.pallet"]
        package_model = self.env["stock.quant.package"]
        created_pallet_lines = actual_pallet_model
        try:
            pallet_count_value = float(pallet_count)
            pallet_count = int(pallet_count_value)
        except (TypeError, ValueError):
            raise UserError(_("Pallet count must be a positive integer."))
        if pallet_count <= 0 or pallet_count != pallet_count_value:
            raise UserError(_("Pallet count must be a positive integer."))
        for rec in self:
            rec.check_unknown_pallet_structure_available()
            rec.clear_actual_pallet_structure_validation()
            starting_number = len(rec.actual_pallet_lines) + 1
            for _pallet_number in range(starting_number, starting_number + pallet_count):
                package = package_model.create({
                    "name": "%s-AUTO" % (rec.reference or rec.billno or "INBOUND"),
                    "package_use": "disposable",
                    "billno": rec.billno,
                    "reference": rec.reference,
                    "cntr_no": rec.cntr_no,
                    "inbound_order_id": rec.id,
                })
                pallet_no = "%s-AUTO-%s" % (rec.reference or rec.billno or "INBOUND", package.id)
                package.write({"name": pallet_no, "original_pallet_no": pallet_no})
                actual_pallet = actual_pallet_model.create({
                    "inbound_order_id": rec.id,
                    "package_id": package.id,
                    "pallet_no": pallet_no,
                })
                package.write({"actual_inbound_pallet_id": actual_pallet.id})
                created_pallet_lines |= actual_pallet
            rec.refresh_actual_pallet_difference_lines()
        return created_pallet_lines

    def get_actual_pallet_binding_scan_state(self, current_actual_pallet_id=False, current_product_id=False):
        result = []
        product_model = self.env["product.product"]
        for rec in self:
            expected_quantity_by_product = rec.get_unknown_expected_quantity_by_product()
            actual_quantity_by_product = rec.get_unknown_actual_quantity_by_product()
            actual_pallet_lines = rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void")
            current_actual_pallet = actual_pallet_lines.filtered(lambda pallet: pallet.id == current_actual_pallet_id)[:1]
            pallet_data = []
            current_pallet_data = {}
            for actual_pallet in actual_pallet_lines:
                pallet_values = {
                    "id": actual_pallet.id,
                    "pallet_no": actual_pallet.pallet_no,
                    "package_id": actual_pallet.package_id.id,
                    "package_barcode": actual_pallet.package_id.barcode,
                    "state": actual_pallet.state,
                    "product_lines": [{
                        "id": product_line.id,
                        "product_id": product_line.product_id.id,
                        "product_name": product_line.product_id.display_name,
                        "product_barcode": product_line.product_id.barcode or "",
                        "default_code": product_line.product_id.default_code or "",
                        "tracking": product_line.product_id.tracking,
                        "quantity": product_line.quantity,
                        "tracking_lines": [{"number": serial_line.serial_number, "quantity": serial_line.quantity} for serial_line in product_line.serial_lines],
                    } for product_line in actual_pallet.product_lines],
                }
                pallet_data.append(pallet_values)
                if actual_pallet == current_actual_pallet:
                    current_pallet_data = pallet_values
            expected_products = []
            for product_id, expected_quantity in expected_quantity_by_product.items():
                product = product_model.sudo().browse(product_id).exists()
                if not product:
                    continue
                expected_products.append({
                    "product_id": product.id,
                    "product_name": product.display_name,
                    "expected_quantity": expected_quantity,
                    "actual_quantity": actual_quantity_by_product.get(product.id, 0.0),
                    "remaining_quantity": expected_quantity - actual_quantity_by_product.get(product.id, 0.0),
                })
            current_product = product_model.sudo().browse(current_product_id).exists() if current_product_id else product_model
            result.append({
                "inbound": {"id": rec.id, "billno": rec.billno or "", "reference": rec.reference or "", "state": rec.state},
                "current_pallet": current_pallet_data,
                "current_product": {"id": current_product.id, "name": current_product.name, "display_name": current_product.display_name, "barcode": current_product.barcode or "", "default_code": current_product.default_code or "", "tracking": current_product.tracking} if current_product else {},
                "summary": {"total_pallets": len(actual_pallet_lines), "ready_pallets": len(actual_pallet_lines.filtered(lambda pallet: pallet.state == "ready")), "pending_pallets": len(actual_pallet_lines.filtered(lambda pallet: pallet.state != "ready")), "expected_quantity": sum(expected_quantity_by_product.values()), "actual_quantity": sum(actual_quantity_by_product.values()), "remaining_quantity": max(sum(expected_quantity_by_product.values()) - sum(actual_quantity_by_product.values()), 0.0)},
                "pallets": pallet_data,
                "expected_products": expected_products,
            })
        return result[0] if len(result) == 1 else result

    def get_unknown_expected_quantity_by_product(self):
        quantity_by_product = defaultdict(float)
        for rec in self:
            for pallet_line in rec.inbound_order_product_ids:
                for product_line in pallet_line.inbound_order_product_pallet_ids:
                    quantity_by_product[product_line.product_id.id] += product_line.quantity * pallet_line.pallets
        return quantity_by_product

    def get_unknown_actual_quantity_by_product(self):
        quantity_by_product = defaultdict(float)
        for rec in self:
            for actual_pallet in rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void"):
                for product_line in actual_pallet.product_lines:
                    quantity_by_product[product_line.product_id.id] += product_line.quantity
        return quantity_by_product

    def validate_unknown_pallet_structure(self, check_quantities=True):
        product_model = self.env["product.product"]
        lot_model = self.env["stock.lot"]
        quant_model = self.env["stock.quant"]
        for rec in self:
            if rec.project.pallet_structure_mode != "unknown":
                continue
            if rec.project.package_generation_mode != "inbound":
                raise UserError(_("Unknown Pallet Structure requires Package Generation Mode to be Inbound."))
            expected_quantity_by_product = rec.get_unknown_expected_quantity_by_product()
            if not expected_quantity_by_product:
                raise UserError(_("Inbound order must contain expected product lines before binding actual pallets."))
            rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void" and not pallet.product_lines).write({"state": "void"})
            actual_pallet_lines = rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void")
            if not actual_pallet_lines:
                raise UserError(_("Create and bind at least one actual pallet before confirming the inbound order."))
            package_ids = set()
            actual_quantity_by_product = defaultdict(float)
            for actual_pallet in actual_pallet_lines:
                if not actual_pallet.package_id or not actual_pallet.package_id.barcode:
                    raise UserError(_("Actual pallet %s has no system package barcode.") % actual_pallet.display_name)
                if actual_pallet.package_id.id in package_ids:
                    raise UserError(_("A system package cannot be assigned to more than one actual pallet."))
                package_ids.add(actual_pallet.package_id.id)
                if not actual_pallet.product_lines:
                    raise UserError(_("Actual pallet %s has no product lines.") % actual_pallet.pallet_no)
                for product_line in actual_pallet.product_lines:
                    product = product_line.product_id
                    if not product or product_line.quantity <= 0:
                        raise UserError(_("Actual pallet product lines require a product and a positive quantity."))
                    actual_quantity_by_product[product.id] += product_line.quantity
                    tracking_quantity = sum(product_line.serial_lines.mapped("quantity"))
                    if product.tracking == "lot" and float_compare(product_line.quantity, tracking_quantity, precision_rounding=product.uom_id.rounding):
                        raise UserError(_("Tracking quantities for product %s must equal the actual pallet product quantity.") % product.display_name)
                    if product.tracking == "serial":
                        if not product_line.serial_lines:
                            raise UserError(_("All serial numbers for product %s must be maintained on the actual pallet before validation.") % product.display_name)
                        if float_compare(product_line.quantity, tracking_quantity, precision_rounding=product.uom_id.rounding):
                            raise UserError(_("Serial number quantities for product %s must equal the actual pallet product quantity.") % product.display_name)
                    if product.tracking != "serial":
                        continue
                    for serial_line in product_line.serial_lines:
                        lot_ids = lot_model.sudo().search([("name", "=", serial_line.serial_number), ("product_id", "=", product.id)])
                        if lot_ids and quant_model.sudo().search([("lot_id", "in", lot_ids.ids), ("quantity", ">", 0)], limit=1):
                            raise UserError(_("Serial number %s already has stock in this company.") % serial_line.serial_number)
            if check_quantities:
                expected_product_ids = set(expected_quantity_by_product)
                actual_product_ids = set(actual_quantity_by_product)
                if expected_product_ids != actual_product_ids:
                    raise UserError(_("Actual pallet products must match the inbound expected products."))
                for product_id, expected_quantity in expected_quantity_by_product.items():
                    product = product_model.sudo().browse(product_id).exists()
                    rounding = product.uom_id.rounding if product else 0.000001
                    if float_compare(actual_quantity_by_product[product_id], expected_quantity, precision_rounding=rounding):
                        raise UserError(_("Actual quantity for product %s must equal the expected inbound quantity.") % (product.display_name if product else product_id))
                actual_pallet_lines.write({"state": "ready"})
        return True

    def refresh_actual_pallet_difference_lines(self):
        difference_model = self.env["world.depot.inbound.order.actual.pallet.difference"]
        product_model = self.env["product.product"]
        for rec in self:
            expected_quantity_by_product = rec.get_unknown_expected_quantity_by_product()
            actual_quantity_by_product = rec.get_unknown_actual_quantity_by_product()
            product_ids = set(expected_quantity_by_product) | set(actual_quantity_by_product)
            difference_by_product_id = {difference.product_id.id: difference for difference in rec.actual_pallet_difference_lines}
            for product_id in sorted(product_ids):
                product = product_model.sudo().browse(product_id).exists()
                if not product:
                    continue
                expected_quantity = expected_quantity_by_product.get(product.id, 0.0)
                actual_quantity = actual_quantity_by_product.get(product.id, 0.0)
                difference_line = difference_by_product_id.pop(product.id, difference_model)
                if not float_compare(actual_quantity, expected_quantity, precision_rounding=product.uom_id.rounding):
                    difference_line.unlink()
                    continue
                pallet_quantity_by_id = defaultdict(float)
                for actual_pallet in rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void"):
                    for product_line in actual_pallet.product_lines.filtered(lambda line: line.product_id == product):
                        pallet_quantity_by_id[actual_pallet.id] += product_line.quantity
                pallet_quantity_lines = [(0, 0, {"actual_pallet_id": actual_pallet_id, "quantity": quantity}) for actual_pallet_id, quantity in pallet_quantity_by_id.items()]
                values = {"original_quantity": expected_quantity, "actual_scanned_quantity": actual_quantity, "difference_quantity": actual_quantity - expected_quantity, "actual_pallet_count": len(pallet_quantity_by_id), "pallet_quantity_lines": [(5, 0, 0)] + pallet_quantity_lines}
                if difference_line:
                    difference_line.write(values)
                else:
                    difference_model.create(dict(values, inbound_order_id=rec.id, product_id=product.id))
            for difference_line in difference_by_product_id.values():
                difference_line.unlink()
        return True

    def action_validate_actual_pallets(self):
        for rec in self:
            if rec.project.pallet_structure_mode != "unknown":
                raise UserError(_("This validation is only available for Unknown Pallet Structure."))
            if rec.state != "new":
                raise UserError(_("Actual pallets can only be validated before the inbound order is confirmed."))
            rec.check_actual_pallet_structure_editable()
            rec.validate_unknown_pallet_structure(check_quantities=False)
            rec.refresh_actual_pallet_difference_lines()
            if rec.actual_pallet_difference_lines:
                rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void").write({"state": "binding"})
                rec.write({"actual_pallet_structure_validated": False})
                return {"type": "ir.actions.client", "tag": "display_notification", "params": {"title": _("Actual Pallet Difference Found"), "message": _("Actual pallet differences were generated. Confirm the difference before confirming the inbound order or creating the receipt."), "type": "warning", "sticky": True, "next": {"type": "ir.actions.client", "tag": "reload"}}}
            rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void").write({"state": "ready"})
            rec.write({"actual_pallet_structure_validated": True})
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"title": _("Actual Pallets Validated"), "message": _("Actual pallet product quantities match the inbound demand."), "type": "success", "sticky": False, "next": {"type": "ir.actions.client", "tag": "reload"}}}

    def action_confirm_actual_pallet_difference(self):
        for rec in self:
            if rec.project.pallet_structure_mode != "unknown":
                raise UserError(_("This confirmation is only available for Unknown Pallet Structure."))
            rec.check_actual_pallet_structure_editable()
            rec.validate_unknown_pallet_structure(check_quantities=False)
            rec.refresh_actual_pallet_difference_lines()
            if not rec.actual_pallet_difference_lines:
                raise UserError(_("There is no actual pallet difference to confirm."))
            rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void").write({"state": "ready"})
            rec.write({"actual_pallet_structure_validated": True, "actual_pallet_difference_confirmed": True, "actual_pallet_difference_confirmed_by_id": self.env.user.id, "actual_pallet_difference_confirmed_datetime": fields.Datetime.now()})
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"title": _("Actual Pallet Difference Confirmed"), "message": _("Actual pallet differences are confirmed and the actual pallet structure is locked."), "type": "success", "sticky": False, "next": {"type": "ir.actions.client", "tag": "reload"}}}

    def action_export_actual_pallet_difference_excel(self):
        attachment_model = self.env["ir.attachment"]
        action = False
        for rec in self:
            if not rec.actual_pallet_difference_lines:
                raise UserError(_("There is no actual pallet difference to export."))
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            worksheet = workbook.add_worksheet("Actual Pallet Difference")
            title_format = workbook.add_format({"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"})
            header_format = workbook.add_format({"bold": True, "align": "center", "valign": "vcenter", "text_wrap": True, "bg_color": "#D9EAF7", "border": 1})
            text_format = workbook.add_format({"border": 1, "valign": "vcenter", "text_wrap": True})
            number_format = workbook.add_format({"border": 1, "valign": "vcenter", "align": "right", "num_format": "0.00"})
            headers = ["Product", "Tracking", "Original Quantity", "Actual Scanned Quantity", "Difference", "Pallet No.", "Quantity on Pallet"]
            worksheet.merge_range(0, 0, 0, len(headers) - 1, "%s - %s" % (_("Actual Pallet Difference"), rec.display_name), title_format)
            for column_index, header in enumerate(headers):
                worksheet.write(2, column_index, header, header_format)
            row_index = 3
            tracking_labels = {"none": "None", "lot": "Lot", "serial": "Serial"}
            for difference_line in rec.actual_pallet_difference_lines:
                pallet_quantity_lines = difference_line.pallet_quantity_lines or self.env["world.depot.inbound.order.actual.pallet.difference.pallet"]
                for pallet_quantity_line in pallet_quantity_lines or [False]:
                    values = [difference_line.product_id.display_name, tracking_labels.get(difference_line.product_tracking, difference_line.product_tracking or ""), difference_line.original_quantity, difference_line.actual_scanned_quantity, difference_line.difference_quantity, pallet_quantity_line.pallet_no if pallet_quantity_line else "", pallet_quantity_line.quantity if pallet_quantity_line else 0.0]
                    for column_index, value in enumerate(values):
                        worksheet.write_number(row_index, column_index, value, number_format) if isinstance(value, (int, float)) and not isinstance(value, bool) else worksheet.write(row_index, column_index, value or "", text_format)
                    row_index += 1
            worksheet.freeze_panes(3, 0)
            worksheet.autofilter(2, 0, max(2, row_index - 1), len(headers) - 1)
            worksheet.set_column(0, 0, 42)
            worksheet.set_column(1, 1, 12)
            worksheet.set_column(2, 4, 20)
            worksheet.set_column(5, 5, 28)
            worksheet.set_column(6, 6, 20)
            workbook.close()
            file_name = (rec.display_name or str(rec.id)).replace("/", "-").replace("\\", "-")
            attachment = attachment_model.create({"name": "Actual_Pallet_Difference_%s.xlsx" % file_name, "type": "binary", "datas": base64.b64encode(output.getvalue()), "res_model": rec._name, "res_id": rec.id, "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
            action = {"type": "ir.actions.act_url", "url": "/web/content/%s?download=true" % attachment.id, "target": "self"}
        return action

    def action_create_unknown_pallet_stock_picking(self):
        picking_model = self.env["stock.picking"]
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        created_picking_count = 0
        for rec in self:
            if rec.project.pallet_structure_mode != "unknown":
                raise UserError(_("This receipt action is only available for Unknown Pallet Structure."))
            if rec.state != "confirm":
                raise UserError(_("Stock picking can only be created from confirmed orders."))
            if not rec.pick_type or rec.pick_type.code != "incoming":
                raise UserError(_("An incoming picking type is required to create a receipt."))
            if not rec.pick_type.default_location_src_id or not rec.pick_type.default_location_dest_id:
                raise UserError(_("The incoming picking type must have both source and destination locations."))
            if picking_model.sudo().search([("inbound_order_id", "=", rec.id), ("state", "!=", "cancel")], limit=1):
                raise UserError(_("A stock picking already exists for this Inbound Order."))
            rec.check_actual_pallet_structure_validated()
            product_move_data = {}
            for actual_pallet in rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void"):
                for product_line in actual_pallet.product_lines:
                    product_data = product_move_data.setdefault(product_line.product_id.id, {"product": product_line.product_id, "quantity": 0.0})
                    product_data["quantity"] += product_line.quantity
            picking = picking_model.create({
                "picking_type_id": rec.pick_type.id,
                "location_id": rec.pick_type.default_location_src_id.id,
                "location_dest_id": rec.pick_type.default_location_dest_id.id,
                "origin": rec.billno,
                "partner_id": rec.owner.id,
                "owner_id": rec.owner.id,
                "inbound_order_id": rec.id,
                "bill_of_lading": rec.bl_no,
                "cntrno": rec.cntr_no,
                "ref_1": rec.reference,
                "planning_date": rec.a_date,
                "project_id": rec.project.id,
            })
            product_moves = {}
            for product_id, product_data in product_move_data.items():
                product = product_data["product"]
                product_moves[product_id] = move_model.create({
                    "name": product.display_name,
                    "product_id": product.id,
                    "product_uom_qty": product_data["quantity"],
                    "product_uom": product.uom_id.id,
                    "picking_id": picking.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "description_picking": _("Inbound receipt for %s") % product.display_name,
                })
            for actual_pallet in rec.actual_pallet_lines.filtered(lambda pallet: pallet.state != "void"):
                for product_line in actual_pallet.product_lines:
                    product = product_line.product_id
                    move_line_values = {
                        "picking_id": picking.id,
                        "move_id": product_moves[product.id].id,
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "location_id": picking.location_id.id,
                        "location_dest_id": picking.location_dest_id.id,
                        "result_package_id": actual_pallet.package_id.id,
                    }
                    if product.tracking == "serial":
                        if not product_line.serial_lines:
                            raise UserError(_("All serial numbers for product %s must be maintained before creating the receipt.") % product.display_name)
                        for serial_line in product_line.serial_lines:
                            move_line_model.create(dict(move_line_values, quantity=1.0, lot_id=False, lot_name=serial_line.serial_number))
                    elif product.tracking == "lot":
                        for serial_line in product_line.serial_lines:
                            move_line_model.create(dict(move_line_values, quantity=serial_line.quantity, lot_id=False, lot_name=serial_line.serial_number))
                    else:
                        move_line_model.create(dict(move_line_values, quantity=product_line.quantity, lot_id=False, lot_name=False))
            rec.write({"stock_picking_id": picking.id})
            created_picking_count += 1
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Stock Picking Created"),
                "message": _("Created %s receipt(s).") % created_picking_count,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }


class InboundActualPallet(models.Model):
    _name = "world.depot.inbound.order.actual.pallet"
    _description = "Actual Inbound Pallet"
    _order = "id desc"
    _sql_constraints = [
        ("actual_inbound_pallet_package_unique", "unique(package_id)", "A package can only be assigned to one actual pallet."),
        ("actual_inbound_pallet_no_unique", "unique(inbound_order_id, pallet_no)", "Actual pallet number must be unique on an inbound order."),
    ]

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", required=True, copy=False, index=True, ondelete="cascade")
    actual_pallet_structure_locked = fields.Boolean(related="inbound_order_id.actual_pallet_structure_locked", string="Actual Pallet Structure Locked", readonly=True)
    package_id = fields.Many2one("stock.quant.package", string="Package", required=True, readonly=True, copy=False, index=True, ondelete="restrict")
    pallet_no = fields.Char(string="Pallet No", required=True, readonly=True, copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("binding", "Binding"), ("ready", "Ready"), ("void", "Void")], string="State", default="draft", required=True, copy=False, index=True)
    product_lines = fields.One2many("world.depot.inbound.order.actual.pallet.product", "actual_pallet_id", string="Products", copy=False)
    tracking_lines = fields.One2many("world.depot.inbound.order.actual.pallet.product.serial", "actual_pallet_id", string="Lot / Serial Numbers", copy=False)

    def action_void_actual_pallet(self):
        picking_model = self.env["stock.picking"]
        for rec in self:
            if rec.state == "void":
                continue
            rec.inbound_order_id.check_actual_pallet_structure_editable()
            if rec.inbound_order_id.state != "new":
                raise UserError(_("Actual pallets can only be voided before the inbound order is confirmed."))
            if picking_model.sudo().search([("inbound_order_id", "=", rec.inbound_order_id.id), ("state", "!=", "cancel")], limit=1):
                raise UserError(_("Actual pallets cannot be voided after a receipt exists."))
            if rec.product_lines or rec.product_lines.mapped("serial_lines"):
                raise UserError(_("Only empty actual pallets can be voided."))
            rec.write({"state": "void"})
            rec.inbound_order_id.clear_actual_pallet_structure_validation()
            rec.inbound_order_id.refresh_actual_pallet_difference_lines()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_complete_actual_pallet_binding(self):
        for rec in self:
            rec.inbound_order_id.check_actual_pallet_structure_editable()
            if rec.inbound_order_id.state != "new":
                raise UserError(_("Actual pallet binding can only be completed before the inbound order is confirmed."))
            if rec.state == "void":
                raise UserError(_("A void actual pallet cannot be completed."))
            if not rec.product_lines:
                raise UserError(_("Actual pallet must contain at least one product line."))
            for product_line in rec.product_lines:
                if not product_line.product_id or product_line.quantity <= 0:
                    raise UserError(_("Actual pallet product lines require a product and a positive quantity."))
                tracking_quantity = sum(product_line.serial_lines.mapped("quantity"))
                if product_line.product_id.tracking == "lot" and float_compare(product_line.quantity, tracking_quantity, precision_rounding=product_line.product_id.uom_id.rounding):
                    raise UserError(_("Tracking quantities for product %s must equal the actual pallet product quantity.") % product_line.product_id.display_name)
                if product_line.product_id.tracking == "serial":
                    if not product_line.serial_lines:
                        raise UserError(_("All serial numbers for product %s must be maintained before completing the actual pallet.") % product_line.product_id.display_name)
                    if float_compare(product_line.quantity, tracking_quantity, precision_rounding=product_line.product_id.uom_id.rounding):
                        raise UserError(_("Serial number quantities for product %s must equal the actual pallet product quantity.") % product_line.product_id.display_name)
            rec.write({"state": "ready"})
        return {"type": "ir.actions.client", "tag": "reload"}


class InboundActualPalletProduct(models.Model):
    _name = "world.depot.inbound.order.actual.pallet.product"
    _description = "Actual Inbound Pallet Product"
    _rec_name = "product_id"
    _order = "id desc"

    actual_pallet_id = fields.Many2one("world.depot.inbound.order.actual.pallet", string="Actual Pallet", required=True, copy=False, index=True, ondelete="cascade")
    inbound_order_id = fields.Many2one(related="actual_pallet_id.inbound_order_id", string="Inbound Order", store=True, readonly=True, index=True)
    product_id = fields.Many2one("product.product", string="Product", required=True, index=True, ondelete="restrict")
    product_tracking = fields.Selection(related="product_id.tracking", string="Tracking", readonly=True)
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    serial_lines = fields.One2many("world.depot.inbound.order.actual.pallet.product.serial", "actual_pallet_product_id", string="Lot / Serial Numbers", copy=False)
    available_product_line_ids = fields.Many2many("product.product", "wd_actual_pallet_product_available_rel", "actual_pallet_product_id", "product_id", string="Available Products", compute="_compute_available_product_line_ids", store=True, readonly=True, copy=False)

    @api.depends("actual_pallet_id.inbound_order_id.inbound_order_product_ids.inbound_order_product_pallet_ids.product_id")
    def _compute_available_product_line_ids(self):
        for rec in self:
            rec.available_product_line_ids = rec.actual_pallet_id.inbound_order_id.inbound_order_product_ids.mapped("inbound_order_product_pallet_ids.product_id")

    @api.onchange("serial_lines")
    def update_tracking_quantity_onchange(self):
        for rec in self:
            if rec.product_tracking in ("serial", "lot"):
                rec.quantity = sum(rec.serial_lines.mapped("quantity"))

    @api.model_create_multi
    def create(self, values_list):
        actual_pallet_model = self.env["world.depot.inbound.order.actual.pallet"]
        actual_pallet_ids = [values.get("actual_pallet_id") for values in values_list if values.get("actual_pallet_id")]
        actual_pallet_model.sudo().browse(actual_pallet_ids).exists().mapped("inbound_order_id").check_actual_pallet_structure_editable()
        records = super().create(values_list)
        records.mapped("inbound_order_id").clear_actual_pallet_structure_validation()
        records.mapped("actual_pallet_id").filtered(lambda pallet: pallet.state == "ready").write({"state": "binding"})
        records.mapped("inbound_order_id").refresh_actual_pallet_difference_lines()
        return records

    def write(self, values):
        self.mapped("inbound_order_id").check_actual_pallet_structure_editable()
        actual_pallet_lines = self.mapped("actual_pallet_id")
        result = super().write(values)
        self.mapped("inbound_order_id").clear_actual_pallet_structure_validation()
        (actual_pallet_lines | self.mapped("actual_pallet_id")).filtered(lambda pallet: pallet.state == "ready").write({"state": "binding"})
        self.mapped("inbound_order_id").refresh_actual_pallet_difference_lines()
        return result

    def unlink(self):
        self.mapped("inbound_order_id").check_actual_pallet_structure_editable()
        actual_pallet_lines = self.mapped("actual_pallet_id")
        inbound_orders = self.mapped("inbound_order_id")
        result = super().unlink()
        inbound_orders.clear_actual_pallet_structure_validation()
        actual_pallet_lines.exists().filtered(lambda pallet: pallet.state == "ready").write({"state": "binding"})
        inbound_orders.refresh_actual_pallet_difference_lines()
        return result

    def sync_tracking_quantity(self):
        for rec in self:
            if rec.product_tracking in ("serial", "lot"):
                quantity = sum(rec.serial_lines.mapped("quantity"))
                if rec.quantity != quantity:
                    rec.write({"quantity": quantity})

    @api.constrains("product_id", "quantity")
    def check_actual_pallet_product_values(self):
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError(_("Actual pallet product quantity cannot be negative."))

    @api.constrains("actual_pallet_id", "product_id")
    def check_actual_pallet_product_expected_product(self):
        for rec in self:
            expected_quantity_by_product = rec.actual_pallet_id.inbound_order_id.get_unknown_expected_quantity_by_product()
            if rec.product_id and rec.product_id.id not in expected_quantity_by_product:
                raise ValidationError(_("Product %s is not expected on inbound order %s.") % (rec.product_id.display_name, rec.inbound_order_id.display_name))


class InboundActualPalletProductSerial(models.Model):
    _name = "world.depot.inbound.order.actual.pallet.product.serial"
    _description = "Actual Inbound Pallet Product Serial"
    _order = "id desc"

    actual_pallet_id = fields.Many2one("world.depot.inbound.order.actual.pallet", string="Actual Pallet", required=True, copy=False, index=True, ondelete="cascade")
    actual_pallet_product_id = fields.Many2one("world.depot.inbound.order.actual.pallet.product", string="Actual Pallet Product", required=True, copy=False, index=True, ondelete="cascade")
    inbound_order_id = fields.Many2one(related="actual_pallet_product_id.inbound_order_id", string="Inbound Order", store=True, readonly=True, index=True)
    product_id = fields.Many2one(related="actual_pallet_product_id.product_id", string="Product", store=True, readonly=True, index=True)
    serial_number = fields.Char(string="Lot / Serial Number", required=True, copy=False, index=True)
    quantity = fields.Float(string="Quantity", required=True, default=1.0)

    @api.model_create_multi
    def create(self, values_list):
        product_model = self.env["world.depot.inbound.order.actual.pallet.product"]
        actual_pallet_product_ids = [values.get("actual_pallet_product_id") for values in values_list if values.get("actual_pallet_product_id")]
        product_model.sudo().browse(actual_pallet_product_ids).exists().mapped("inbound_order_id").check_actual_pallet_structure_editable()
        records = super().create(values_list)
        records.mapped("inbound_order_id").clear_actual_pallet_structure_validation()
        records.mapped("actual_pallet_product_id").sync_tracking_quantity()
        records.mapped("inbound_order_id").refresh_actual_pallet_difference_lines()
        return records

    def write(self, values):
        self.mapped("inbound_order_id").check_actual_pallet_structure_editable()
        product_lines = self.mapped("actual_pallet_product_id")
        result = super().write(values)
        self.mapped("inbound_order_id").clear_actual_pallet_structure_validation()
        (product_lines | self.mapped("actual_pallet_product_id")).sync_tracking_quantity()
        self.mapped("inbound_order_id").refresh_actual_pallet_difference_lines()
        return result

    def unlink(self):
        self.mapped("inbound_order_id").check_actual_pallet_structure_editable()
        product_lines = self.mapped("actual_pallet_product_id")
        inbound_orders = self.mapped("inbound_order_id")
        result = super().unlink()
        inbound_orders.clear_actual_pallet_structure_validation()
        product_lines.exists().sync_tracking_quantity()
        inbound_orders.refresh_actual_pallet_difference_lines()
        return result

    @api.constrains("serial_number", "quantity", "product_id", "inbound_order_id")
    def check_tracking_number(self):
        for rec in self:
            if not (rec.serial_number or "").strip():
                raise ValidationError(_("Lot / Serial Number is required."))
            if rec.quantity <= 0:
                raise ValidationError(_("Lot / Serial Number quantity must be greater than zero."))
            if rec.product_id.tracking != "serial":
                continue
            if float_compare(rec.quantity, 1.0, precision_rounding=rec.product_id.uom_id.rounding):
                raise ValidationError(_("Serial number quantity must be one."))
            duplicate_serial = self.sudo().search([("inbound_order_id", "=", rec.inbound_order_id.id), ("product_id", "=", rec.product_id.id), ("serial_number", "=", rec.serial_number), ("id", "!=", rec.id)], limit=1)
            if duplicate_serial:
                raise ValidationError(_("The same serial number can only be bound once on an inbound order for one product."))

    @api.constrains("actual_pallet_id", "actual_pallet_product_id")
    def check_actual_pallet_product_link(self):
        for rec in self:
            if rec.actual_pallet_id != rec.actual_pallet_product_id.actual_pallet_id:
                raise ValidationError(_("The selected product must belong to the actual pallet."))


class InboundActualPalletDifference(models.Model):
    _name = "world.depot.inbound.order.actual.pallet.difference"
    _description = "Actual Inbound Pallet Difference"
    _order = "id desc"

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", required=True, readonly=True, copy=False, index=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Product", required=True, readonly=True, copy=False, index=True, ondelete="restrict")
    product_tracking = fields.Selection(related="product_id.tracking", string="Tracking", readonly=True)
    original_quantity = fields.Float(string="Original Quantity", readonly=True)
    actual_scanned_quantity = fields.Float(string="Actual Scanned Quantity", readonly=True)
    difference_quantity = fields.Float(string="Difference", readonly=True)
    actual_pallet_count = fields.Integer(string="Actual Pallet Count", readonly=True)
    pallet_quantity_lines = fields.One2many("world.depot.inbound.order.actual.pallet.difference.pallet", "difference_line_id", string="Actual Pallets", readonly=True, copy=False)


class InboundActualPalletDifferencePallet(models.Model):
    _name = "world.depot.inbound.order.actual.pallet.difference.pallet"
    _description = "Actual Inbound Pallet Difference Pallet"
    _order = "id desc"

    difference_line_id = fields.Many2one("world.depot.inbound.order.actual.pallet.difference", string="Actual Pallet Difference", required=True, readonly=True, copy=False, index=True, ondelete="cascade")
    actual_pallet_id = fields.Many2one("world.depot.inbound.order.actual.pallet", string="Actual Pallet", required=True, readonly=True, copy=False, index=True, ondelete="restrict")
    pallet_no = fields.Char(related="actual_pallet_id.pallet_no", string="Pallet No.", readonly=True)
    quantity = fields.Float(string="Quantity on Pallet", readonly=True)


class StockBarcodeLiteScanService(models.AbstractModel):
    _inherit = "stock.barcode.lite.scan.service"

    @api.model
    def build_actual_pallet_binding_result(self, result_type, barcode_type, message, barcode="", inbound_order=False, actual_pallet_id=False, product_id=False, tracking_number=False, action_name=False, success=True, next_step="scan_inbound"):
        last_scan = {"barcode": barcode or "", "type": result_type, "barcode_type": barcode_type, "message": message}
        scan_state = inbound_order.get_actual_pallet_binding_scan_state(actual_pallet_id, product_id) if inbound_order else {"inbound": {}, "current_pallet": {}, "current_product": {}, "summary": {"total_pallets": 0, "ready_pallets": 0, "pending_pallets": 0, "expected_quantity": 0.0, "actual_quantity": 0.0, "remaining_quantity": 0.0}, "pallets": [], "expected_products": []}
        scan_state["last_scan"] = last_scan
        return {"success": success, "type": result_type, "barcode": barcode or "", "barcode_type": barcode_type, "message": message, "next_step": next_step, "current": {"inbound_order_id": inbound_order.id if inbound_order else False, "actual_pallet_id": actual_pallet_id, "product_id": product_id, "tracking_number": tracking_number or False}, "action": {"name": action_name or result_type}, "scan_state": scan_state}

    @api.model
    def get_actual_pallet_binding_completion_step(self, inbound_order):
        expected_quantity_by_product = inbound_order.get_unknown_expected_quantity_by_product()
        if not expected_quantity_by_product:
            return "scan_product"
        actual_quantity_by_product = inbound_order.get_unknown_actual_quantity_by_product()
        product_model = self.env["product.product"]
        for product_id, expected_quantity in expected_quantity_by_product.items():
            product = product_model.sudo().browse(product_id).exists()
            if not product or float_compare(actual_quantity_by_product.get(product.id, 0.0), expected_quantity, precision_rounding=product.uom_id.rounding):
                return "scan_product"
        return "validate"

    @api.model
    def process_actual_pallet_binding_validate(self, inbound_order_id, current_actual_pallet_id=False, current_product_id=False):
        inbound_order_model = self.env["world.depot.inbound.order"]
        inbound_order_result = inbound_order_model.sudo().search([("id", "=", inbound_order_id)], limit=1)
        if not inbound_order_result:
            return self.build_actual_pallet_binding_result("error", _("Validation"), _("Inbound order was not found."), action_name="validate_actual_pallets", success=False)
        inbound_order = inbound_order_model.browse(inbound_order_result.id)
        if inbound_order.project.pallet_structure_mode != "unknown":
            return self.build_actual_pallet_binding_result("error", _("Validation"), _("This inbound order does not use actual pallet binding."), inbound_order=inbound_order, action_name="validate_actual_pallets", success=False)
        try:
            inbound_order.action_validate_actual_pallets()
        except UserError as error:
            return self.build_actual_pallet_binding_result("error", _("Validation"), error.args[0], inbound_order=inbound_order, action_name="validate_actual_pallets", success=False, next_step="scan_package")
        if not inbound_order.actual_pallet_structure_validated:
            return self.build_actual_pallet_binding_result("error", _("Validation"), _("Actual pallet differences were generated. Confirm the difference before confirming the inbound order or creating the receipt."), inbound_order=inbound_order, action_name="validate_actual_pallets", success=False, next_step="scan_package")
        result = self.build_actual_pallet_binding_result("validation", _("Validation"), _("Actual pallet product quantities match the inbound demand."), inbound_order=inbound_order, action_name="validate_actual_pallets", next_step="scan_inbound")
        result.pop("scan_state", None)
        return result

    @api.model
    def process_actual_pallet_binding_scan(self, code, inbound_order_id=False, current_actual_pallet_id=False, current_product_id=False, current_tracking_number=False, quantity=False):
        inbound_order_model = self.env["world.depot.inbound.order"]
        actual_pallet_model = self.env["world.depot.inbound.order.actual.pallet"]
        actual_product_model = self.env["world.depot.inbound.order.actual.pallet.product"]
        actual_serial_model = self.env["world.depot.inbound.order.actual.pallet.product.serial"]
        product_model = self.env["product.product"]
        lot_model = self.env["stock.lot"]
        quant_model = self.env["stock.quant"]
        code = (code or "").strip()
        if not inbound_order_id:
            if not code:
                return self.build_actual_pallet_binding_result("error", _("Error"), _("Please scan an inbound order QR code."), action_name="scan_error", success=False)
            inbound_orders = inbound_order_model.sudo().search([("billno", "=", code)], limit=2)
            if not inbound_orders:
                return self.build_actual_pallet_binding_result("error", _("Error"), _("No inbound order matches QR code %s.") % code, barcode=code, action_name="scan_inbound", success=False)
            if len(inbound_orders) > 1:
                return self.build_actual_pallet_binding_result("error", _("Error"), _("Multiple inbound orders match QR code %s.") % code, barcode=code, action_name="scan_inbound", success=False)
            inbound_order = inbound_order_model.browse(inbound_orders.id)
            if inbound_order.project.pallet_structure_mode != "unknown":
                return self.build_actual_pallet_binding_result("error", _("Error"), _("This inbound order does not use actual pallet binding."), barcode=code, action_name="scan_inbound", success=False)
            if inbound_order.state != "new":
                return self.build_actual_pallet_binding_result("error", _("Error"), _("Actual pallet binding is only available before the inbound order is confirmed."), barcode=code, action_name="scan_inbound", success=False)
            return self.build_actual_pallet_binding_result("inbound", _("Inbound"), _("Inbound order %s selected.") % inbound_order.billno, barcode=code, inbound_order=inbound_order, action_name="select_inbound", next_step="scan_package")
        inbound_order = inbound_order_model.sudo().search([("id", "=", inbound_order_id)], limit=1)
        if not inbound_order:
            return self.build_actual_pallet_binding_result("error", _("Error"), _("Inbound order was not found."), barcode=code, action_name="scan_inbound", success=False)
        if inbound_order.project.pallet_structure_mode != "unknown":
            return self.build_actual_pallet_binding_result("error", _("Error"), _("This inbound order does not use actual pallet binding."), barcode=code, action_name="scan_inbound", success=False)
        is_quantity_input = bool(current_actual_pallet_id and current_product_id and quantity is not False and quantity is not None)
        if not code and not is_quantity_input:
            return self.build_actual_pallet_binding_result("error", _("Error"), _("Please scan a barcode."), inbound_order=inbound_order, actual_pallet_id=current_actual_pallet_id, product_id=current_product_id, tracking_number=current_tracking_number, action_name="scan_error", success=False, next_step="scan_package")
        actual_pallet_result = actual_pallet_model.sudo().search([("id", "=", current_actual_pallet_id), ("inbound_order_id", "=", inbound_order.id), ("state", "!=", "void")], limit=1) if current_actual_pallet_id else actual_pallet_model
        actual_pallet = actual_pallet_model.browse(actual_pallet_result.id) if actual_pallet_result else actual_pallet_model
        package = self.env["stock.quant.package"].sudo().search([("barcode", "=", code)], limit=1) if code and not is_quantity_input else self.env["stock.quant.package"]
        if package:
            scanned_pallet = actual_pallet_model.sudo().search([("package_id", "=", package.id), ("inbound_order_id", "=", inbound_order.id), ("state", "!=", "void")], limit=1)
            if not scanned_pallet:
                return self.build_actual_pallet_binding_result("error", _("Pallet"), _("Package %s is not an active actual pallet on this inbound order.") % package.display_name, barcode=code, inbound_order=inbound_order, action_name="scan_package", success=False, next_step="scan_package")
            scanned_pallet = actual_pallet_model.browse(scanned_pallet.id)
            if scanned_pallet.state == "draft":
                scanned_pallet.write({"state": "binding"})
            return self.build_actual_pallet_binding_result("pallet", _("Pallet"), _("Actual pallet %s selected.") % scanned_pallet.pallet_no, barcode=code, inbound_order=inbound_order, actual_pallet_id=scanned_pallet.id, action_name="select_pallet", next_step="scan_product")
        if not actual_pallet:
            return self.build_actual_pallet_binding_result("error", _("Error"), _("Please scan an active actual pallet first."), barcode=code, inbound_order=inbound_order, action_name="missing_pallet", success=False, next_step="scan_package")
        expected_quantity_by_product = inbound_order.get_unknown_expected_quantity_by_product()
        scanned_product = product_model.sudo().search([("id", "in", list(expected_quantity_by_product)), "|", ("barcode", "=", code), ("default_code", "=", code)], limit=1) if code and not is_quantity_input else product_model
        if not current_product_id or scanned_product:
            if not scanned_product:
                return self.build_actual_pallet_binding_result("error", _("Product"), _("Scanned product is not expected on this inbound order."), barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, action_name="scan_product", success=False, next_step="scan_product")
            actual_quantity_by_product = inbound_order.get_unknown_actual_quantity_by_product()
            if float_compare(actual_quantity_by_product.get(scanned_product.id, 0.0), expected_quantity_by_product[scanned_product.id], precision_rounding=scanned_product.uom_id.rounding) >= 0:
                next_step = self.get_actual_pallet_binding_completion_step(inbound_order)
                return self.build_actual_pallet_binding_result("product", _("Product"), _("Product %s is already complete.") % scanned_product.display_name, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=scanned_product.id, action_name="select_completed_product", next_step=next_step)
            next_step = "scan_serial" if scanned_product.tracking == "serial" else "scan_lot" if scanned_product.tracking == "lot" else "input_quantity"
            return self.build_actual_pallet_binding_result("product", _("Product"), _("Product %s selected.") % scanned_product.display_name, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=scanned_product.id, action_name="select_product", next_step=next_step)
        product = product_model.sudo().search([("id", "=", current_product_id), ("id", "in", list(expected_quantity_by_product))], limit=1)
        if not product:
            return self.build_actual_pallet_binding_result("error", _("Product"), _("Current product is not expected on this inbound order."), barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, action_name="scan_product", success=False, next_step="scan_product")
        actual_quantity_by_product = inbound_order.get_unknown_actual_quantity_by_product()
        if product.tracking == "serial":
            serial_numbers = [serial_number.strip() for serial_number in re.split(r"[,，\r\n]+", code) if serial_number.strip()]
            if not serial_numbers:
                return self.build_actual_pallet_binding_result("error", _("Serial Number"), _("Please scan a serial number."), barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="scan_serial", success=False, next_step="scan_serial")
            if len(serial_numbers) != len(set(serial_numbers)):
                return self.build_actual_pallet_binding_result("error", _("Serial Number"), _("The scanned serial number list contains duplicates."), barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="scan_serial", success=False, next_step="scan_serial")
            existing_serial = actual_serial_model.sudo().search([("inbound_order_id", "=", inbound_order.id), ("product_id", "=", product.id), ("serial_number", "in", serial_numbers)], limit=1)
            if existing_serial:
                return self.build_actual_pallet_binding_result("error", _("Serial Number"), _("Serial number %s was already scanned.") % existing_serial.serial_number, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="scan_serial", success=False, next_step="scan_serial")
            lot_ids = lot_model.sudo().search([("name", "in", serial_numbers), ("product_id", "=", product.id)])
            existing_quant = quant_model.sudo().search([("lot_id", "in", lot_ids.ids), ("quantity", ">", 0)], limit=1)
            if existing_quant:
                return self.build_actual_pallet_binding_result("error", _("Serial Number"), _("Serial number %s already has stock in this company.") % existing_quant.lot_id.name, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="scan_serial", success=False, next_step="scan_serial")
            if float_compare(actual_quantity_by_product.get(product.id, 0.0) + len(serial_numbers), expected_quantity_by_product[product.id], precision_rounding=product.uom_id.rounding) > 0:
                return self.build_actual_pallet_binding_result("error", _("Serial Number"), _("Scanned quantity exceeds the expected inbound quantity for %s.") % product.display_name, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="scan_serial", success=False, next_step="scan_serial")
            product_line = actual_product_model.sudo().search([("actual_pallet_id", "=", actual_pallet.id), ("product_id", "=", product.id)], limit=1)
            if product_line:
                product_line = actual_product_model.browse(product_line.id)
                if actual_pallet.state == "ready":
                    actual_pallet.write({"state": "binding"})
                product_line.write({"quantity": product_line.quantity + len(serial_numbers)})
            else:
                if actual_pallet.state == "ready":
                    actual_pallet.write({"state": "binding"})
                product_line = actual_product_model.create({"actual_pallet_id": actual_pallet.id, "product_id": product.id, "quantity": len(serial_numbers)})
            actual_serial_model.create([{"actual_pallet_id": actual_pallet.id, "actual_pallet_product_id": product_line.id, "serial_number": serial_number, "quantity": 1.0} for serial_number in serial_numbers])
            next_step = self.get_actual_pallet_binding_completion_step(inbound_order) if float_compare(actual_quantity_by_product.get(product.id, 0.0) + len(serial_numbers), expected_quantity_by_product[product.id], precision_rounding=product.uom_id.rounding) == 0 else "scan_serial"
            return self.build_actual_pallet_binding_result("serial", _("Serial Number"), _("Added %s serial number(s).") % len(serial_numbers), barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="add_serial", next_step=next_step)
        if product.tracking == "lot" and not current_tracking_number and quantity is False:
            return self.build_actual_pallet_binding_result("lot", _("Lot"), _("Lot %s selected.") % code, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, tracking_number=code, action_name="select_lot", next_step="input_quantity")
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            return self.build_actual_pallet_binding_result("error", _("Quantity"), _("Quantity is required for product %s.") % product.display_name, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, tracking_number=current_tracking_number, action_name="input_quantity", success=False, next_step="input_quantity")
        if quantity <= 0:
            return self.build_actual_pallet_binding_result("error", _("Quantity"), _("Quantity must be greater than zero."), barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, tracking_number=current_tracking_number, action_name="input_quantity", success=False, next_step="input_quantity")
        if float_compare(actual_quantity_by_product.get(product.id, 0.0) + quantity, expected_quantity_by_product[product.id], precision_rounding=product.uom_id.rounding) > 0:
            return self.build_actual_pallet_binding_result("error", _("Quantity"), _("Scanned quantity exceeds the expected inbound quantity for %s.") % product.display_name, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, tracking_number=current_tracking_number, action_name="input_quantity", success=False, next_step="input_quantity")
        if product.tracking == "lot" and not current_tracking_number:
            return self.build_actual_pallet_binding_result("error", _("Lot"), _("Lot number is required for product %s.") % product.display_name, barcode=code, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="scan_lot", success=False, next_step="scan_lot")
        product_line = actual_product_model.sudo().search([("actual_pallet_id", "=", actual_pallet.id), ("product_id", "=", product.id)], limit=1)
        if product_line:
            product_line = actual_product_model.browse(product_line.id)
            if actual_pallet.state == "ready":
                actual_pallet.write({"state": "binding"})
            product_line.write({"quantity": product_line.quantity + quantity})
        else:
            if actual_pallet.state == "ready":
                actual_pallet.write({"state": "binding"})
            product_line = actual_product_model.create({"actual_pallet_id": actual_pallet.id, "product_id": product.id, "quantity": quantity})
        if product.tracking == "lot":
            tracking_line_result = actual_serial_model.sudo().search([("actual_pallet_product_id", "=", product_line.id), ("serial_number", "=", current_tracking_number)], limit=1)
            if tracking_line_result:
                actual_serial_model.browse(tracking_line_result.id).write({"quantity": tracking_line_result.quantity + quantity})
            else:
                actual_serial_model.create({"actual_pallet_id": actual_pallet.id, "actual_pallet_product_id": product_line.id, "serial_number": current_tracking_number, "quantity": quantity})
        next_step = self.get_actual_pallet_binding_completion_step(inbound_order) if float_compare(actual_quantity_by_product.get(product.id, 0.0) + quantity, expected_quantity_by_product[product.id], precision_rounding=product.uom_id.rounding) == 0 else "scan_product"
        return self.build_actual_pallet_binding_result("quantity", _("Quantity"), _("Quantity added for %s.") % product.display_name, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="add_quantity", next_step=next_step)

    @api.model
    def process_actual_pallet_binding_void(self, inbound_order_id, actual_pallet_id):
        inbound_order_model = self.env["world.depot.inbound.order"]
        actual_pallet_model = self.env["world.depot.inbound.order.actual.pallet"]
        inbound_order_result = inbound_order_model.sudo().search([("id", "=", inbound_order_id)], limit=1)
        if not inbound_order_result:
            return self.build_actual_pallet_binding_result("error", _("Pallet"), _("Inbound order was not found."), action_name="void_actual_pallet", success=False)
        inbound_order = inbound_order_model.browse(inbound_order_result.id)
        if inbound_order.project.pallet_structure_mode != "unknown":
            return self.build_actual_pallet_binding_result("error", _("Pallet"), _("This inbound order does not use actual pallet binding."), inbound_order=inbound_order, action_name="void_actual_pallet", success=False)
        actual_pallet_result = actual_pallet_model.sudo().search([("id", "=", actual_pallet_id), ("inbound_order_id", "=", inbound_order.id), ("state", "!=", "void")], limit=1)
        if not actual_pallet_result:
            return self.build_actual_pallet_binding_result("error", _("Pallet"), _("Actual pallet was not found or is already voided."), inbound_order=inbound_order, action_name="void_actual_pallet", success=False)
        actual_pallet = actual_pallet_model.browse(actual_pallet_result.id)
        try:
            actual_pallet.action_void_actual_pallet()
        except UserError as error:
            return self.build_actual_pallet_binding_result("error", _("Pallet"), error.args[0], inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, action_name="void_actual_pallet", success=False, next_step="scan_product")
        return self.build_actual_pallet_binding_result("void", _("Pallet"), _("Actual pallet %s was voided.") % actual_pallet.pallet_no, inbound_order=inbound_order, action_name="void_actual_pallet", next_step="scan_package")

    @api.model
    def process_actual_pallet_binding_edit(self, operation, inbound_order_id, actual_pallet_id, actual_pallet_product_id=False, actual_pallet_tracking_id=False, quantity=False):
        inbound_order_model = self.env["world.depot.inbound.order"]
        actual_pallet_model = self.env["world.depot.inbound.order.actual.pallet"]
        actual_product_model = self.env["world.depot.inbound.order.actual.pallet.product"]
        actual_serial_model = self.env["world.depot.inbound.order.actual.pallet.product.serial"]
        inbound_order_result = inbound_order_model.sudo().search([("id", "=", inbound_order_id)], limit=1)
        if not inbound_order_result:
            return self.build_actual_pallet_binding_result("error", _("Edit"), _("Inbound order was not found."), action_name="edit_actual_pallet", success=False)
        inbound_order = inbound_order_model.browse(inbound_order_result.id)
        if inbound_order.project.pallet_structure_mode != "unknown":
            return self.build_actual_pallet_binding_result("error", _("Edit"), _("This inbound order does not use actual pallet binding."), inbound_order=inbound_order, action_name="edit_actual_pallet", success=False)
        if inbound_order.state != "new":
            return self.build_actual_pallet_binding_result("error", _("Edit"), _("Actual pallet binding can only be edited before the inbound order is confirmed."), inbound_order=inbound_order, action_name="edit_actual_pallet", success=False)
        actual_pallet_result = actual_pallet_model.sudo().search([("id", "=", actual_pallet_id), ("inbound_order_id", "=", inbound_order.id), ("state", "!=", "void")], limit=1)
        if not actual_pallet_result:
            return self.build_actual_pallet_binding_result("error", _("Edit"), _("Actual pallet was not found."), inbound_order=inbound_order, action_name="edit_actual_pallet", success=False)
        actual_pallet = actual_pallet_model.browse(actual_pallet_result.id)
        if operation not in ("delete_product", "delete_tracking", "update_quantity"):
            return self.build_actual_pallet_binding_result("error", _("Edit"), _("Unsupported actual pallet edit operation."), inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, action_name="edit_actual_pallet", success=False, next_step="scan_product")
        product_line_result = actual_product_model.sudo().search([("id", "=", actual_pallet_product_id), ("actual_pallet_id", "=", actual_pallet.id)], limit=1)
        if not product_line_result:
            return self.build_actual_pallet_binding_result("error", _("Edit"), _("Actual pallet product was not found."), inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, action_name="edit_actual_pallet", success=False, next_step="scan_product")
        product_line = actual_product_model.browse(product_line_result.id)
        product = product_line.product_id
        tracking_line = actual_serial_model
        if operation == "delete_product":
            if actual_pallet.state == "ready":
                actual_pallet.write({"state": "binding"})
            product_line.unlink()
            message = _("Product %s was deleted from the actual pallet.") % product.display_name
        else:
            tracking_line_result = actual_serial_model.sudo().search([("id", "=", actual_pallet_tracking_id), ("actual_pallet_product_id", "=", product_line.id)], limit=1)
            if operation == "delete_tracking" and not tracking_line_result:
                return self.build_actual_pallet_binding_result("error", _("Edit"), _("Lot or serial number was not found on the selected product."), inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="delete_tracking", success=False, next_step="scan_product")
            if operation == "update_quantity" and product.tracking == "serial":
                return self.build_actual_pallet_binding_result("error", _("Edit"), _("Serial number quantities cannot be changed. Delete the serial number and scan it again."), inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="update_quantity", success=False, next_step="scan_product")
            if operation == "update_quantity" and product.tracking == "lot" and not tracking_line_result:
                return self.build_actual_pallet_binding_result("error", _("Edit"), _("Batch quantity changes require the actual pallet product and batch record."), inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="update_quantity", success=False, next_step="scan_product")
            if tracking_line_result:
                tracking_line = actual_serial_model.browse(tracking_line_result.id)
            if operation == "delete_tracking":
                remaining_quantity = product_line.quantity - tracking_line.quantity
                tracking_number = tracking_line.serial_number
                if actual_pallet.state == "ready":
                    actual_pallet.write({"state": "binding"})
                tracking_line.unlink()
                if float_compare(remaining_quantity, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                    product_line.unlink()
                else:
                    product_line.write({"quantity": remaining_quantity})
                message = _("Lot or serial number %s was deleted.") % tracking_number
            else:
                try:
                    quantity = float(quantity)
                except (TypeError, ValueError):
                    return self.build_actual_pallet_binding_result("error", _("Quantity"), _("Quantity is required."), inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="update_quantity", success=False, next_step="scan_product")
                if float_compare(quantity, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                    return self.build_actual_pallet_binding_result("error", _("Quantity"), _("Quantity must be greater than zero."), inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="update_quantity", success=False, next_step="scan_product")
                expected_quantity = inbound_order.get_unknown_expected_quantity_by_product().get(product.id, 0.0)
                actual_quantity = inbound_order.get_unknown_actual_quantity_by_product().get(product.id, 0.0)
                current_quantity = tracking_line.quantity if product.tracking == "lot" else product_line.quantity
                if float_compare(actual_quantity - current_quantity + quantity, expected_quantity, precision_rounding=product.uom_id.rounding) > 0:
                    return self.build_actual_pallet_binding_result("error", _("Quantity"), _("Quantity exceeds the expected inbound quantity for %s.") % product.display_name, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name="update_quantity", success=False, next_step="scan_product")
                if actual_pallet.state == "ready":
                    actual_pallet.write({"state": "binding"})
                if product.tracking == "lot":
                    tracking_line.write({"quantity": quantity})
                    product_line.write({"quantity": product_line.quantity - current_quantity + quantity})
                else:
                    product_line.write({"quantity": quantity})
                message = _("Quantity for %s was updated.") % product.display_name
        return self.build_actual_pallet_binding_result("edit", _("Edit"), message, inbound_order=inbound_order, actual_pallet_id=actual_pallet.id, product_id=product.id, action_name=operation, next_step=self.get_actual_pallet_binding_completion_step(inbound_order))
