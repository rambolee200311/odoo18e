# -*- coding: utf-8 -*-

import math
from psycopg2 import sql

from odoo import _, fields, models, api
from odoo.exceptions import UserError

class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"
    _order = "id desc"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    cwarehouseid = fields.Char(string="U8C Warehouse ID", copy=False, index=True)
    source_sale_delivery_reference = fields.Char(string="Source Sale Delivery Reference", copy=False, index=True)
    vsourcebillcode = fields.Char(string="Source Bill Code", copy=False, index=True)
    project_package_generation_mode = fields.Selection(related="project.package_generation_mode", string="Package Generation Mode", readonly=True)
    organic = fields.Boolean(string="Organic", copy=False, index=True)

    @api.onchange("project")
    def onchange_project_warehouse(self):
        for record in self:
            record.warehouse = record.project.warehouse
            record.pick_type = record.project.inbound_pick_type


    def action_open_sunrise_inbound_pallet_products(self):
        for rec in self:
            if rec.project_name != "SUNRISE":
                raise UserError(_("Only SUNRISE inbound orders can open pallet products."))

            return {
                "type": "ir.actions.act_window",
                "name": _("Pallet Products"),
                "res_model": "world.depot.inbound.order.products.pallet",
                "view_mode": "list,form",
                "views": [(False, "list"), (False, "form")],
                "domain": [
                    ("inbound_order_product_id.inbound_order_id", "=", rec.id),
                ],
                "context": {
                    "list_view_ref": "stock_barcode_lite.view_stock_barcode_lite_sunrise_inbound_pallet_product_list",
                    "form_view_ref": "stock_barcode_lite.view_stock_barcode_lite_sunrise_inbound_pallet_product_form",
                },
            }
        return False
    def action_confirm(self):
        for rec in self:
            if rec.project.name == "SUNRISE":
                rec.validate_sunrise_inbound_confirm_values()
        return super().action_confirm()

    # @api.depends("inbound_order_product_ids.inbound_order_product_pallet_ids.product_id.product_tmpl_id.organic")
    # def _compute_organic(self):
    #     for rec in self:
    #         detail_line_list = rec.inbound_order_product_ids.mapped("inbound_order_product_pallet_ids")
    #         rec.organic = any(detail_line_list.mapped("product_id.product_tmpl_id.organic"))

    def validate_sunrise_inbound_confirm_values(self):
        for rec in self:
            missing_fields = []
            if not rec.date:
                missing_fields.append(rec._fields["date"].string)
            if not rec.a_date:
                missing_fields.append(rec._fields["a_date"].string)
            if not rec.cwarehouseid:
                missing_fields.append(rec._fields["cwarehouseid"].string)
            if not rec.vsourcebillcode:
                missing_fields.append(rec._fields["vsourcebillcode"].string)
            if rec.type == "service" and not rec.source_sale_delivery_reference:
                missing_fields.append(rec._fields["source_sale_delivery_reference"].string)

            if missing_fields:
                raise UserError(_("Sunrise inbound order %s is missing required fields: %s") % (rec.reference or rec.billno or rec.id, ", ".join(missing_fields)))
            for pallet_index, pallet_line in enumerate(rec.inbound_order_product_ids, start=1):
                pallet_missing_fields = []
                if not pallet_line.pallet_no:
                    pallet_missing_fields.append(pallet_line._fields["pallet_no"].string)
                if not pallet_line.inbound_order_product_pallet_ids:
                    pallet_missing_fields.append(
                        pallet_line._fields["inbound_order_product_pallet_ids"].string
                    )

                if pallet_missing_fields:
                    raise UserError(_("Sunrise inbound pallet line %s is missing required fields: %s") % (pallet_index, ", ".join(pallet_missing_fields)))

                if rec.project_package_generation_mode == "inbound" and not pallet_line.package_id:
                    raise UserError(
                        _('Pallet "%s" has no package. Generate packages before confirming the inbound order.')
                        % pallet_line.pallet_no
                    )

                if rec.project_package_generation_mode == "none" and pallet_line.package_id:
                    raise UserError(
                        _('Pallet "%s" has a package although Package Generation Mode is No Package.')
                        % pallet_line.pallet_no
                    )

                for detail_index, detail_line in enumerate(pallet_line.inbound_order_product_pallet_ids, start=1):
                    line_name = _("Pallet %s, product line %s") % (pallet_line.pallet_no or pallet_index, detail_index)
                    line_missing_fields = []

                    if not detail_line.product_id:
                        line_missing_fields.append(detail_line._fields["product_id"].string)
                    if pallet_line.creation_source in ("api", "import") and not detail_line.source_product_code:
                        line_missing_fields.append(detail_line._fields["source_product_code"].string)
                    if not detail_line.cprojectid:
                        line_missing_fields.append(detail_line._fields["cprojectid"].string)
                    if not detail_line.ndiscounttaxtype:
                        line_missing_fields.append(detail_line._fields["ndiscounttaxtype"].string)
                    if not detail_line.vsourcebillcode:
                        line_missing_fields.append(detail_line._fields["vsourcebillcode"].string)
                    if not detail_line.vsourcerowno:
                        line_missing_fields.append(detail_line._fields["vsourcerowno"].string)
                    if not detail_line.cspaceid:
                        line_missing_fields.append(detail_line._fields["cspaceid"].string)
                    if not detail_line.box_type:
                        line_missing_fields.append(detail_line._fields["box_type"].string)
                    if not detail_line.castunitid:
                        line_missing_fields.append(detail_line._fields["castunitid"].string)
                    if not detail_line.u8_aux_uom_name:
                        line_missing_fields.append(detail_line._fields["u8_aux_uom_name"].string)
                    if not detail_line.is_lot:
                        line_missing_fields.append(detail_line._fields["is_lot"].string)
                    if detail_line.is_lot == "Y" and not detail_line.lot_name:
                        line_missing_fields.append(detail_line._fields["lot_name"].string)
                    # if not detail_line.gross_weight:
                    #     line_missing_fields.append(detail_line._fields["gross_weight"].string)
                    # if not detail_line.pallet_dimensions:
                    #     line_missing_fields.append(detail_line._fields["pallet_dimensions"].string)

                    if line_missing_fields:
                        raise UserError(_("%s is missing required fields: %s") % (line_name, ", ".join(line_missing_fields)))
                    if detail_line.vsourcebillcode != rec.vsourcebillcode:
                        raise UserError(_("%s vsourcebillcode must equal inbound order vsourcebillcode.") % line_name)

                    if detail_line.box_type not in ("full", "partial"):
                        raise UserError(_("%s box_type must be full or partial.") % line_name)
                    if detail_line.box_qty <= 0:
                        raise UserError(_("%s box_qty must be greater than 0.") % line_name)
                    if detail_line.box_in_qty <= 0:
                        raise UserError(_("%s box_in_qty must be greater than 0.") % line_name)
                    if detail_line.ninnum <= 0:
                        raise UserError(_("%s ninnum must be greater than 0.") % line_name)
                    if detail_line.u8_aux_qty <= 0:
                        raise UserError(_("%s u8_aux_qty must be greater than 0.") % line_name)
                    if detail_line.u8_conversion_rate <= 0:
                        raise UserError(_("%s u8_conversion_rate must be greater than 0.") % line_name)

                    expected_ninnum = detail_line.box_qty * detail_line.box_in_qty
                    if not math.isclose(
                            detail_line.ninnum,
                            expected_ninnum,
                            rel_tol=1e-9,
                            abs_tol=1e-6,
                    ):
                        raise UserError(_("%s ninnum must equal box_qty * box_in_qty.") % line_name)

                    if detail_line.box_type == "full" and not math.isclose(
                            detail_line.box_in_qty,
                            detail_line.u8_conversion_rate,
                            rel_tol=1e-9,
                            abs_tol=1e-6,
                    ):
                        raise UserError(
                            _("%s box_in_qty must equal u8_conversion_rate when box_type is full.")
                            % line_name
                        )

                    if detail_line.box_type == "partial" and math.isclose(
                            detail_line.box_in_qty,
                            detail_line.u8_conversion_rate,
                            rel_tol=1e-9,
                            abs_tol=1e-6,
                    ):
                        raise UserError(
                            _("%s box_in_qty must not equal u8_conversion_rate when box_type is partial.")
                            % line_name
                        )

                pallet_line.validate_sunrise_physical_pallet_identity()

            #rec.validate_sunrise_product_specifications()

    def validate_sunrise_product_specifications(self):
        detail_line_model = self.env["world.depot.inbound.order.products.pallet"]
        for rec in self:
            grouped_detail_lines = {}
            for pallet_line in rec.inbound_order_product_ids:
                for detail_line in pallet_line.inbound_order_product_pallet_ids:
                    specification_key = (
                        pallet_line.pallet_no,
                        detail_line.product_id.id,
                        (detail_line.lot_name or "").strip() if detail_line.is_lot == "Y" else "",
                    )
                    if specification_key not in grouped_detail_lines:
                        grouped_detail_lines[specification_key] = detail_line_model
                    grouped_detail_lines[specification_key] |= detail_line

            for detail_lines in grouped_detail_lines.values():
                detail_lines.get_sunrise_product_specification()
        return True


    def action_cancel(self):
        normal_records = self.env["world.depot.inbound.order"]

        for rec in self:
            if rec.project.name != "SUNRISE":
                normal_records |= rec
                continue

            if rec.state == "cancel":
                raise UserError(_("This order %s has already been canceled.") % rec.reference)

            picking = rec.stock_picking_id
            if rec.state == "confirm" and picking:
                if picking.state == "done":
                    remaining_qty = rec.get_sunrise_done_inbound_remaining_stock_qty(picking)
                    if remaining_qty > 0:
                        raise UserError(
                            _("Inbound order %s has a done receipt. Please return all received stock manually before cancelling. Remaining stock qty: %s")
                            % (rec.reference, remaining_qty)
                        )
                    rec.action_archive_sunrise_packages_before_cancel()
                    rec.write({"state": "cancel"})
                    continue

                try:
                    picking.unlink()
                except Exception as error:
                    raise UserError(
                        _("Failed to delete stock picking for order %s: %s")
                        % (rec.reference, str(error))
                    )
                rec.action_delete_sunrise_packages_before_cancel()
            else:
                rec.action_delete_sunrise_packages_before_cancel()
            rec.write({"state": "cancel"})

        if normal_records:
            return super(InboundOrder, normal_records).action_cancel()

        return True

    def unlink(self):
        for rec in self:
            if rec.project.name == "SUNRISE":
                rec.action_delete_sunrise_packages_before_cancel()
        return super().unlink()

    def action_delete_sunrise_packages_before_cancel(self):
        for rec in self:
            rec.inbound_order_product_ids.delete_sunrise_packages_without_stock()

        return True

    def action_archive_sunrise_packages_before_cancel(self):
        package_model = self.env["stock.quant.package"]

        for rec in self:
            for pallet_line in rec.inbound_order_product_ids:
                if pallet_line.is_reused_package:
                    continue
                package = pallet_line.package_id
                if not package:
                    continue

                package_name = package.name or package.barcode
                package_barcode = package.barcode or package.name
                if not package_name and not package_barcode:
                    continue

                if "-CANCEL-" in package_name or "-CANCEL-" in package_barcode:
                    continue

                archive_name = "%s-CANCEL-%s" % (package_name, rec.billno or rec.reference or rec.id)
                archive_barcode = "%s-CANCEL-%s" % (package_barcode, rec.billno or rec.reference or rec.id)
                existing_package = package_model.sudo().search([
                    "|",
                    ("name", "=", archive_name),
                    ("barcode", "=", archive_barcode),
                    ("id", "!=", package.id),
                ], limit=1)
                if existing_package:
                    archive_name = "%s-%s" % (archive_name, rec.id)
                    archive_barcode = "%s-%s" % (archive_barcode, rec.id)

                package.write({
                    "name": archive_name,
                    "barcode": archive_barcode,
                })

        return True

    def get_sunrise_done_inbound_remaining_stock_qty(self, picking):
        quant_model = self.env["stock.quant"]
        total_qty = 0.0

        move_lines = picking.sudo().move_line_ids.filtered(
            lambda line: line.result_package_id and line.product_id and line.quantity > 0
        )

        for move_line in move_lines:
            domain = [
                ("package_id", "=", move_line.result_package_id.id),
                ("product_id", "=", move_line.product_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ]
            if move_line.lot_id:
                domain.append(("lot_id", "=", move_line.lot_id.id))

            quant_list = quant_model.sudo().search(domain)
            for quant in quant_list:
                total_qty += max((quant.quantity or 0.0) - (quant.reserved_quantity or 0.0), 0.0)

        return total_qty


    def action_open_inbound_product_import_wizard(self):
        for rec in self:
            if rec.state != "new":
                raise UserError(_("Only new inbound orders can import products."))
            if rec.inbound_order_product_ids:
                raise UserError(_("This inbound order already has pallet/product lines."))
            return {
                "type": "ir.actions.act_window",
                "name": _("Import Products"),
                "res_model": "inbound.product.import.wizard",
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "new",
                "context": {
                    "default_inbound_order_id": rec.id,
                },
            }
        return False

    def action_open_sunrise_pallet_label_list(self):
        for rec in self:
            if rec.state != "confirm":
                raise UserError(_("Only confirmed inbound orders can print pallet labels."))

            pallet_lines = rec.inbound_order_product_ids.filtered(lambda line: not line.is_reused_package)
            if not pallet_lines:
                raise UserError(_("This inbound order has no complete pallet labels available for printing."))

            return {
                "type": "ir.actions.act_window",
                "name": _("Select Pallets to Print"),
                "res_model": "world.depot.inbound.order.product",
                "view_mode": "list",
                "views": [(self.env.ref("stock_barcode_lite.view_sunrise_inbound_pallet_label_list").id, "list")],
                "domain": [("id", "in", pallet_lines.ids)],
                "context": {
                    "create": False,
                    "edit": False,
                    "delete": False,
                },
            }
        return False

    def action_sunrise_generate_packages(self):
        picking_model = self.env["stock.picking"]
        created_count = 0

        for rec in self:
            if rec.project.name != "SUNRISE":
                raise UserError(_("Only SUNRISE inbound orders can generate packages."))
            if rec.project_package_generation_mode != "inbound":
                raise UserError(_("Package Generation Mode must be Inbound."))
            if rec.state != "new":
                raise UserError(_("Packages can only be generated before the inbound order is confirmed."))

            existing_picking = picking_model.sudo().search([
                ("inbound_order_id", "=", rec.id),
                ("state", "!=", "cancel"),
            ], limit=1)
            if existing_picking:
                raise UserError(_("Packages cannot be generated after a stock picking exists."))

            pending_pallet_lines = rec.inbound_order_product_ids.filtered(lambda pallet_line: not pallet_line.package_id)
            for pallet_line in pending_pallet_lines:
                if pallet_line.pallets != 1:
                    raise UserError(
                        _('Pallet "%s" has pallets=%s. Please split pallets before generating packages.')
                        % (pallet_line.pallet_no, pallet_line.pallets)
                    )
                if not pallet_line.pallet_no:
                    raise UserError(_("The pallet number field is required."))
                if not pallet_line.inbound_order_product_pallet_ids:
                    raise UserError(_('Pallet "%s" must contain product lines.') % pallet_line.pallet_no)
                if any(not detail_line.product_id for detail_line in pallet_line.inbound_order_product_pallet_ids):
                    raise UserError(_('Pallet "%s" has a product line without a product.') % pallet_line.pallet_no)
                pallet_line.validate_sunrise_physical_pallet_identity()

            for pallet_line in pending_pallet_lines:
                pallet_line.create_sunrise_package()
                created_count += 1

        if not created_count:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No Packages Generated"),
                    "message": _("Every pallet line already has a package."),
                    "type": "info",
                    "sticky": False,
                },
            }

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Packages Generated"),
                "message": _("Generated %(count)s package(s).") % {"count": created_count},
                "type": "success",
                "sticky": False,
            },
        }

    def validate_sunrise_incoming_stock_picking(self):
        picking_model = self.env["stock.picking"]

        for record in self:
            if record.project.name != "SUNRISE":
                raise UserError(_("Only SUNRISE projects can create a picking."))
            if record.state != "confirm":
                raise UserError(_("Only confirmed records can create a picking."))
            if not record.pick_type:
                raise UserError(_("The pick type field is required."))
            if record.pick_type.code != "incoming":
                raise UserError(_("Please select an incoming pick type."))
            if not record.inbound_order_product_ids:
                raise UserError(_("Please add pallet lines."))
            existing_picking = picking_model.sudo().search([
                ("inbound_order_id", "=", record.id),
                ("state", "!=", "cancel"),
            ], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this record."))
            for pallet_line in record.inbound_order_product_ids:
                if not pallet_line.pallet_no:
                    raise UserError(_("The pallet number field is required."))

                if pallet_line.pallets != 1:
                    raise UserError(
                        _('Pallet "%s" pallets must be 1.')
                        % pallet_line.pallet_no
                    )

                if record.project_package_generation_mode == "inbound" and not pallet_line.package_id:
                    raise UserError(
                        _('Pallet "%s" has no package. Generate packages before confirming the inbound order.')
                        % pallet_line.pallet_no
                    )

                if record.project_package_generation_mode == "none" and pallet_line.package_id:
                    raise UserError(
                        _('Pallet "%s" has a package although Package Generation Mode is No Package.')
                        % pallet_line.pallet_no
                    )

                if pallet_line.is_reused_package:
                    pallet_line.get_sunrise_reused_package_locations()

                if not pallet_line.inbound_order_product_pallet_ids:
                    raise UserError(
                        _('Pallet "%s" must contain product lines.')
                        % pallet_line.pallet_no
                    )

                for detail_line in pallet_line.inbound_order_product_pallet_ids:
                    if not detail_line.product_id:
                        raise UserError(
                            _('Product is required on pallet "%s".')
                            % pallet_line.pallet_no
                        )

                    if detail_line.quantity <= 0:
                        raise UserError(
                            _('Product "%s" quantity must be greater than 0.')
                            % detail_line.product_id.display_name
                        )

                    if detail_line.product_id.tracking == "serial":
                        raise UserError(
                            _('Serial-tracked product "%s" is not supported by Sunrise incoming picking.')
                            % detail_line.product_id.display_name
                        )

                    if detail_line.is_lot == "Y":
                        if detail_line.product_id.tracking != "lot":
                            raise UserError(
                                _('Product "%s" must enable lot tracking.')
                                % detail_line.product_id.display_name
                            )

                        if not detail_line.lot_name:
                            raise UserError(_('Lot number is required for product "%s".')% detail_line.product_id.display_name)

                    elif detail_line.product_id.tracking == "lot":
                        raise UserError(
                            _('Product "%s" enables lot tracking, so is_lot must be Y.')
                            % detail_line.product_id.display_name)

                pallet_line.validate_sunrise_physical_pallet_identity()

        return True


    def action_sunrise_create_incoming_stock_picking(self):
        self.validate_sunrise_incoming_stock_picking()

        picking_model = self.env["stock.picking"]
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        lot_model = self.env["stock.lot"]
        created_package_count = 0

        for record in self:
            generation_mode = record.project_package_generation_mode or "picking"
            reused_package_locations = record.inbound_order_product_ids.get_sunrise_reused_package_locations()
            picking = picking_model.create({
                "picking_type_id": record.pick_type.id,
                "location_id": record.pick_type.default_location_src_id.id,
                "location_dest_id": record.pick_type.default_location_dest_id.id,
                "origin": record.billno,
                "inbound_order_id": record.id,
                "partner_id": record.owner.id,
                "scheduled_date": record.a_date,
                "bill_of_lading": record.bl_no,
                "cntrno": record.cntr_no,
                "ref_1": record.reference,
                "planning_date": record.date,
                "owner_id": record.owner.id,
                "project_id": record.project.id if record.project else False,
            })

            product_move_data = {}

            for pallet_line in record.inbound_order_product_ids:
                for detail_line in pallet_line.inbound_order_product_pallet_ids:
                    product_id = detail_line.product_id.id

                    if product_id not in product_move_data:
                        product_move_data[product_id] = {
                            "product": detail_line.product_id,
                            "quantity": 0.0,
                        }

                    product_move_data[product_id]["quantity"] += detail_line.quantity

            product_moves = {}

            for product_id, move_data in product_move_data.items():
                product = move_data["product"]

                move = move_model.create({
                    "name": product.display_name,
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom_qty": move_data["quantity"],
                    "product_uom": product.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                })

                product_moves[product_id] = move

            for pallet_line in record.inbound_order_product_ids:
                package = pallet_line.package_id
                target_location = reused_package_locations.get(pallet_line.id, picking.location_dest_id)
                if generation_mode == "inbound" and not package:
                    raise UserError(
                        _('Pallet "%s" has no package. Generate packages before confirming the inbound order.')
                        % pallet_line.pallet_no
                    )
                if generation_mode == "picking" and not package:
                    package = pallet_line.create_sunrise_package()
                    created_package_count += 1
                if generation_mode == "none" and package:
                    raise UserError(
                        _('Pallet "%s" has a package although Package Generation Mode is No Package.')
                        % pallet_line.pallet_no
                    )

                for detail_line in pallet_line.inbound_order_product_pallet_ids:
                    product = detail_line.product_id
                    move = product_moves[product.id]
                    lot = False

                    if detail_line.is_lot == "Y":
                        lot = lot_model.sudo().search([
                            ("name", "=", detail_line.lot_name),
                            ("product_id", "=", product.id),
                            ("company_id", "=", picking.company_id.id),
                        ], limit=1)

                        if not lot:
                            lot = lot_model.create({
                                "name": detail_line.lot_name,
                                "product_id": product.id,
                                "company_id": picking.company_id.id,
                            })

                    move_line_values = {
                        "picking_id": picking.id,
                        "move_id": move.id,
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "quantity": detail_line.quantity,
                        "location_id": picking.location_id.id,
                        "location_dest_id": target_location.id,
                        "result_package_id": package.id if package else False,
                        "lot_id": lot.id if lot else False,
                        "inbound_order_product_pallet_id": detail_line.id,
                    }
                    if pallet_line.is_reused_package:
                        move_line_values.update({
                            "is_location_updated": True,
                            "location_updated_by_id": self.env.user.id,
                            "location_updated_datetime": fields.Datetime.now(),
                        })
                    move_line_model.create(move_line_values)

            record.write({
                "stock_picking_id": picking.id,
            })

        if created_package_count:
            return self.env.ref("stock_barcode_lite.action_report_inbound_pallet_label").report_action(self)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Stock picking created successfully."),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "name": _("Inbound Order"),
                    "res_model": "world.depot.inbound.order",
                    "res_id": self[:1].id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "target": "current",
                },
            },
        }


class InboundOrderProduct(models.Model):
    _inherit = "world.depot.inbound.order.product"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    package_id = fields.Many2one("stock.quant.package", string="Package", copy=False, index=True)
    package_barcode = fields.Char(related="package_id.barcode", string="Package Barcode", readonly=True)
    is_reused_package = fields.Boolean(string="Reused Package", default=False, readonly=True, copy=False, index=True)

    def action_print_selected_sunrise_pallet_labels(self):
        if not self:
            raise UserError(_("Select at least one pallet to print."))

        for rec in self:
            inbound_order = rec.inbound_order_id
            if inbound_order.project.name != "SUNRISE":
                raise UserError(_("Pallet \"%s\" is not a SUNRISE pallet.") % rec.pallet_no)
            if inbound_order.state != "confirm":
                raise UserError(_("Pallet \"%s\" belongs to an inbound order that is not confirmed.") % rec.pallet_no)
            if rec.is_reused_package:
                raise UserError(_("Pallet \"%s\" reuses an existing package and cannot print an incomplete label.") % rec.pallet_no)
            if not rec.package_id or not rec.package_id.barcode:
                raise UserError(_("Pallet \"%s\" has no package barcode.") % rec.pallet_no)
            if not rec.inbound_order_product_pallet_ids:
                raise UserError(_("Pallet \"%s\" has no product lines.") % rec.pallet_no)

        inbound_orders = self.mapped("inbound_order_id")
        return self.env.ref("stock_barcode_lite.action_report_inbound_pallet_label").report_action(
            inbound_orders,
            data={"inbound_pallet_ids": self.ids},
        )

    def create_sunrise_package(self):
        self.ensure_one()
        if self.package_id:
            return self.package_id
        inbound_order = self.inbound_order_id
        package_model = self.env["stock.quant.package"]
        package = package_model.create({
            "name": self.get_sunrise_package_name(),
            "barcode": package_model.generate_sunrise_package_barcode(),
            "package_use": "disposable",
            "billno": inbound_order.billno,
            "reference": inbound_order.reference,
            "cntr_no": inbound_order.cntr_no,
            "original_pallet_no": self.pallet_no,
        })
        self.write({"package_id": package.id, "is_reused_package": False})
        return package

    def get_sunrise_physical_pallet_identity(self):
        self.ensure_one()
        identities = set()
        for detail_line in self.inbound_order_product_pallet_ids:
            product_code = (detail_line.source_product_code or detail_line.product_id.barcode or "").strip()
            lot_name = (detail_line.lot_name or "").strip() if detail_line.is_lot == "Y" else ""
            if not product_code:
                raise UserError(_("Pallet \"%s\" has a product line without a source product code.") % self.pallet_no)
            identities.add((product_code, lot_name))
        if len(identities) != 1:
            raise UserError(
                _("Physical pallet \"%s\" must contain one source product and one lot.") % self.pallet_no
            )
        return identities.pop()

    def validate_sunrise_physical_pallet_identity(self):
        for pallet_line in self:
            pallet_line.get_sunrise_physical_pallet_identity()
        return True

    def get_sunrise_reused_package_locations(self):
        locations = {}
        quant_model = self.env["stock.quant"]

        for rec in self:
            if not rec.is_reused_package:
                continue
            if not rec.package_id:
                raise UserError(_('Pallet "%s" is marked as reusing a package but has no package.') % rec.pallet_no)

            quants = quant_model.sudo().search([
                ("package_id", "=", rec.package_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ])
            location_ids = quants.mapped("location_id")
            if len(location_ids) != 1:
                raise UserError(
                    _('Reused package "%s" for pallet "%s" must have exactly one internal stock location.')
                    % (rec.package_id.name or rec.package_id.barcode, rec.pallet_no)
                )
            locations[rec.id] = location_ids

        return locations

    def get_sunrise_package_name(self):
        self.ensure_one()
        product_code, lot_name = self.get_sunrise_physical_pallet_identity()
        return "%s-%s-%s" % (lot_name or "NOLOT", product_code, self.pallet_no)

    def init(self):
        super().init()
        self.migrate_legacy_sunrise_package_links()

    def migrate_legacy_sunrise_package_links(self):
        cr = self.env.cr
        cr.execute(
            """
                SELECT column_name
                  FROM information_schema.columns
                 WHERE table_schema = current_schema()
                   AND table_name = %s
                   AND column_name IN ('package_id', 'sunrise_pallet_no')
            """,
            [self._table],
        )
        columns = {row[0] for row in cr.fetchall()}
        if {"package_id", "sunrise_pallet_no"} - columns:
            return
        cr.execute(
            sql.SQL(
                """
                    UPDATE {table} AS pallet_line
                       SET package_id = package.id
                      FROM stock_quant_package AS package
                     WHERE pallet_line.package_id IS NULL
                       AND COALESCE(pallet_line.sunrise_pallet_no, '') <> ''
                       AND package.barcode = pallet_line.sunrise_pallet_no
                """
            ).format(table=sql.Identifier(self._table))
        )

    def delete_sunrise_packages_without_stock(self):
        quant_model = self.env["stock.quant"]

        for rec in self:
            package = rec.package_id
            if not package or rec.is_reused_package:
                continue
            quant = quant_model.sudo().search([
                ("package_id", "=", package.id),
                ("quantity", "!=", 0),
            ], limit=1)
            if quant:
                raise UserError(
                    _('Pallet No "%s" still has stock and cannot be deleted.')
                    % (package.name or package.barcode)
                )
            rec.write({"package_id": False})
            package.unlink()
        return True

    def unlink(self):
        self.delete_sunrise_packages_without_stock()
        for rec in self:
            if rec.inbound_order_product_pallet_ids:
                rec.inbound_order_product_pallet_ids.unlink()
        return super().unlink()


class InboundOrderProductsPallet(models.Model):
    _inherit = "world.depot.inbound.order.products.pallet"

    inbound_order_id = fields.Many2one('world.depot.inbound.order',related='inbound_order_product_id.inbound_order_id')
    pallet_no = fields.Char(related="inbound_order_product_id.pallet_no", string="Pallet No", store=True, readonly=True,
                            index=True)
    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    source_product_code = fields.Char(string="Source Product Code", copy=False, index=True)
    product_ean = fields.Char(string="Product EAN", copy=False, index=True)
    is_lot = fields.Selection([("N", "No"), ("Y", "Yes")], string="Is Lot", default="Y", copy=False, index=True)
    lot_name = fields.Char(string="Lot Name", copy=False, index=True)

    cprojectid = fields.Char(string="Sunrise Ref", copy=False, index=True)
    ndiscounttaxtype = fields.Char(string="Tax Deduction Type", copy=False, index=True)
    vsourcebillcode = fields.Char(string="Source Bill Code", copy=False, index=True)
    vsourcerowno = fields.Char(string="Source Row No", copy=False, index=True)
    box_type = fields.Selection([("full", "Full"), ("partial", "Non-standard")], string="Box Type", copy=False, index=True)
    box_qty = fields.Integer(string="Box Qty", copy=False)
    ninnum = fields.Float(string="Received Units", copy=False)
    box_in_qty = fields.Float(string="Box In Qty", copy=False)
    u8_aux_qty = fields.Float(string="U8 Aux Qty", copy=False)
    u8_conversion_rate = fields.Float(string="U8 Conversion Rate", copy=False)
    castunitid = fields.Char(string="Assistant Unit", copy=False, index=True)
    u8_aux_uom_name = fields.Char(string="U8 Aux UOM Name", copy=False, index=True)
    m_date = fields.Date(string="Manufacture Date", copy=False)
    e_date = fields.Date(string="Expiration Date", copy=False)
    cspaceid = fields.Char(string="Location Code", copy=False, index=True)
    gross_weight = fields.Char(string="Gross Weight(kg)", copy=False)
    pallet_dimensions = fields.Char(string="Carton Dimensions(m)", copy=False)

    def get_sunrise_product_specification(self, allow_missing=False):
        if not self:
            raise UserError(_("No inbound product detail was found for the Sunrise product specification."))

        specification_values = set()
        has_missing = False
        for rec in self:
            line_name = _("Pallet %s, product %s, lot %s") % (
                rec.pallet_no or "-",
                rec.product_id.display_name or "-",
                rec.lot_name or "-",
            )
            gross_weight_raw = (rec.gross_weight or "").strip() if rec.gross_weight else ""
            pallet_dimensions_raw = "".join((rec.pallet_dimensions or "").upper().split()) if rec.pallet_dimensions else ""

            if not gross_weight_raw or not pallet_dimensions_raw:
                has_missing = True
                if not allow_missing:
                    if not gross_weight_raw:
                        raise UserError(_("%s gross weight must be a valid positive number.") % line_name)
                    if not pallet_dimensions_raw:
                        raise UserError(_("%s carton dimensions must not be blank.") % line_name)
                continue

            try:
                gross_weight = float(gross_weight_raw)
            except (TypeError, ValueError) as error:
                raise UserError(_("%s gross weight must be a valid positive number.") % line_name) from error
            if not math.isfinite(gross_weight) or gross_weight <= 0:
                raise UserError(_("%s gross weight must be a valid positive number.") % line_name)

            specification_values.add((round(gross_weight, 6), pallet_dimensions_raw))

        if has_missing and allow_missing:
            first_line = self[:1]
            return {
                "gross_weight": False,
                "gross_weight_value": False,
                "pallet_dimensions": False,
                "pallet_dimensions_value": False,
                "has_specification": False,
            }

        if len(specification_values) != 1:
            first_line = self[:1]
            raise UserError(
                _("Pallet %s, product %s and lot %s must have the same gross weight and carton dimensions.")
                % (
                    first_line.pallet_no or "-",
                    first_line.product_id.display_name or "-",
                    first_line.lot_name or "-",
                )
            )

        gross_weight_value, pallet_dimensions_value = next(iter(specification_values))
        first_line = self[:1]
        return {
            "gross_weight": first_line.gross_weight,
            "gross_weight_value": gross_weight_value,
            "pallet_dimensions": first_line.pallet_dimensions,
            "pallet_dimensions_value": pallet_dimensions_value,
            "has_specification": True,
        }
