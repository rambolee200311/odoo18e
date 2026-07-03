# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.http import request
from odoo.exceptions import UserError, ValidationError

class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"
    _order = "id desc"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    cwarehouseid = fields.Char(string="U8C Warehouse ID", copy=False, index=True)
    source_sale_delivery_reference = fields.Char(string="Source Sale Delivery Reference", copy=False, index=True)
    vsourcebillcode = fields.Char(string="Source Bill Code", copy=False, index=True)

    def action_confirm(self):
        for rec in self:
            if rec.project.name == "SUNRISE":
                rec.validate_sunrise_inbound_confirm_values()
        return super().action_confirm()

    def validate_sunrise_inbound_confirm_values(self):
        for rec in self:
            missing_fields = []
            if not rec.date:
                missing_fields.append("date")
            if not rec.a_date:
                missing_fields.append("a_date")
            if not rec.cwarehouseid:
                missing_fields.append("cwarehouseid")
            if not rec.vsourcebillcode:
                missing_fields.append("vsourcebillcode")
            if rec.type == "service" and not rec.source_sale_delivery_reference:
                missing_fields.append("source_sale_delivery_reference")

            if missing_fields:
                raise UserError(_("Sunrise inbound order %s is missing required fields: %s") % (rec.reference or rec.billno or rec.id, ", ".join(missing_fields)))

            for pallet_index, pallet_line in enumerate(rec.inbound_order_product_ids, start=1):
                pallet_missing_fields = []
                if not pallet_line.pallet_no:
                    pallet_missing_fields.append("pallet_no")
                if not pallet_line.sunrise_pallet_no:
                    pallet_missing_fields.append("sunrise_pallet_no")
                if not pallet_line.inbound_order_product_pallet_ids:
                    pallet_missing_fields.append("product detail lines")

                if pallet_missing_fields:
                    raise UserError(_("Sunrise inbound pallet line %s is missing required fields: %s") % (pallet_index, ", ".join(pallet_missing_fields)))

                for detail_index, detail_line in enumerate(pallet_line.inbound_order_product_pallet_ids, start=1):
                    line_name = _("Pallet %s, product line %s") % (pallet_line.pallet_no or pallet_index, detail_index)
                    line_missing_fields = []

                    if not detail_line.product_id:
                        line_missing_fields.append("product_id")
                    if not detail_line.cprojectid:
                        line_missing_fields.append("cprojectid")
                    if not detail_line.ndiscounttaxtype:
                        line_missing_fields.append("ndiscounttaxtype")
                    if not detail_line.vsourcebillcode:
                        line_missing_fields.append("vsourcebillcode")
                    if not detail_line.vsourcerowno:
                        line_missing_fields.append("vsourcerowno")
                    if not detail_line.cspaceid:
                        line_missing_fields.append("cspaceid")
                    if not detail_line.box_type:
                        line_missing_fields.append("box_type")
                    if not detail_line.castunitid:
                        line_missing_fields.append("castunitid")
                    if not detail_line.u8_aux_uom_name:
                        line_missing_fields.append("u8_aux_uom_name")
                    if not detail_line.is_lot:
                        line_missing_fields.append("is_lot")
                    if detail_line.is_lot == "Y" and not detail_line.lot_name:
                        line_missing_fields.append("lot_name")

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
                    if abs(detail_line.ninnum - expected_ninnum) > 0.000001:
                        raise UserError(_("%s ninnum must equal box_qty * box_in_qty.") % line_name)

                    if detail_line.box_type == "full" and abs(detail_line.box_in_qty - detail_line.u8_conversion_rate) > 0.000001:
                        raise UserError(_("%s box_in_qty must equal u8_conversion_rate when box_type is full.") % line_name)

                    if detail_line.box_type == "partial" and detail_line.box_in_qty >= detail_line.u8_conversion_rate:
                        raise UserError(_("%s box_in_qty must be less than u8_conversion_rate when box_type is partial.") % line_name)


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
            rec.write({"state": "cancel"})

        if normal_records:
            return super(InboundOrder, normal_records).action_cancel()

        return True

    def action_delete_sunrise_packages_before_cancel(self):
        quant_model = self.env["stock.quant"]

        for rec in self:
            for pallet_line in rec.inbound_order_product_ids:
                package = pallet_line.package_id
                if not package:
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

                pallet_line.write({"package_id": False})
                package.unlink()

        return True

    def action_archive_sunrise_packages_before_cancel(self):
        package_model = self.env["stock.quant.package"]

        for rec in self:
            for pallet_line in rec.inbound_order_product_ids:
                package = pallet_line.package_id
                if not package:
                    continue

                package_name = package.name or package.barcode
                if not package_name:
                    continue

                if "-CANCEL-" in package_name:
                    continue

                archive_name = "%s-CANCEL-%s" % (package_name, rec.billno or rec.reference or rec.id)
                existing_package = package_model.sudo().search([
                    "|",
                    ("name", "=", archive_name),
                    ("barcode", "=", archive_name),
                    ("id", "!=", package.id),
                ], limit=1)
                if existing_package:
                    archive_name = "%s-%s" % (archive_name, rec.id)

                package.write({
                    "name": archive_name,
                    "barcode": archive_name,
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

    def validate_sunrise_incoming_stock_picking(self):
        picking_model = self.env["stock.picking"]
        package_model = self.env["stock.quant.package"]
        package_names = set()

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
                if not pallet_line.sunrise_pallet_no:
                    raise UserError(
                        _('Sunrise pallet number is required for pallet "%s".')
                        % pallet_line.pallet_no
                    )

                if pallet_line.sunrise_pallet_no in package_names:
                    raise UserError(
                        _('Sunrise pallet number "%s" is duplicated.')
                        % pallet_line.sunrise_pallet_no
                    )
                package_names.add(pallet_line.sunrise_pallet_no)

                if pallet_line.pallets != 1:
                    raise UserError(
                        _('Pallet "%s" pallets must be 1.')
                        % pallet_line.pallet_no
                    )

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

        if package_names:
            existing_package  = package_model.sudo().search([
                "|",
                ("name", "in", list(package_names)),
                ("barcode", "in", list(package_names)),
            ], limit=1)

            if existing_package:
                raise UserError(
                    _('Pallet No "%s" already exists as a package. Please cancel/archive the old inbound package before creating a new receipt.')
                    % (existing_package.name or existing_package.barcode)
                )
        return True


    def action_sunrise_create_incoming_stock_picking(self):
        self.validate_sunrise_incoming_stock_picking()

        picking_model = self.env["stock.picking"]
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        package_model = self.env["stock.quant.package"]
        lot_model = self.env["stock.lot"]

        for record in self:
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
                package_name = pallet_line.sunrise_pallet_no

                package = package_model.sudo().search([
                    "|",
                    ("name", "=", package_name),
                    ("barcode", "=", package_name),
                ], limit=1)

                if package:
                    raise UserError(
                        _('Pallet No "%s" already exists as a package. Please cancel/archive the old inbound package before creating a new receipt.')
                        % package_name
                    )
                package = package_model.create({
                    "name": package_name,
                    "barcode": package_name,
                    "package_use": "disposable",
                    "billno": record.billno,
                    "reference": record.reference,
                    "cntr_no": record.cntr_no,
                })

                pallet_line.write({
                    "package_id": package.id,
                })

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

                    move_line_model.create({
                        "picking_id": picking.id,
                        "move_id": move.id,
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "quantity": detail_line.quantity,
                        "location_id": picking.location_id.id,
                        "location_dest_id": picking.location_dest_id.id,
                        "result_package_id": package.id,
                        "lot_id": lot.id if lot else False,
                        "inbound_order_product_pallet_id": detail_line.id,
                    })

            record.write({
                "stock_picking_id": picking.id,
            })

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
    sunrise_pallet_no = fields.Char(string="Sunrise Pallet No", compute="compute_sunrise_pallet_no",store=True, copy=False, index=True)
    package_id = fields.Many2one('stock.quant.package', string='Pallet', index=True)

    @api.depends("pallet_no", "inbound_order_id.cntr_no", "inbound_order_id.project")
    def compute_sunrise_pallet_no(self):
        for rec in self:
            if rec.inbound_order_id.project.name == "SUNRISE" and rec.inbound_order_id.cntr_no and rec.pallet_no:
                rec.sunrise_pallet_no = "%s-%s" % (rec.inbound_order_id.cntr_no, rec.pallet_no)
            else:
                rec.sunrise_pallet_no = False

    @api.constrains("pallet_no", "inbound_order_id", "sunrise_pallet_no")
    def check_sunrise_pallet_no_unique(self):
        pallet_model = self.env["world.depot.inbound.order.product"]

        for rec in self:
            if rec.inbound_order_id.project.name != "SUNRISE":
                continue
            if not rec.pallet_no or not rec.inbound_order_id:
                continue
            existing_pallet_no = pallet_model.sudo().search([
                ("id", "!=", rec.id),
                ("pallet_no", "=", rec.pallet_no),
                ("inbound_order_id.project", "=", rec.inbound_order_id.project.id),
                ("inbound_order_id.state", "!=", "cancel"),
            ], limit=1)
            if existing_pallet_no:
                raise ValidationError(
                    _('Pallet No "%s" already exists in inbound order "%s".')
                    % (rec.pallet_no,existing_pallet_no.inbound_order_id.billno or existing_pallet_no.inbound_order_id.reference,))
            if not rec.sunrise_pallet_no or rec.inbound_order_id.state == "cancel":
                continue

            existing_sunrise_pallet_no = pallet_model.sudo().search([
                ("id", "!=", rec.id),
                ("sunrise_pallet_no", "=", rec.sunrise_pallet_no),
                ("inbound_order_id.project", "=", rec.inbound_order_id.project.id),
                ("inbound_order_id.state", "!=", "cancel"),
                ("inbound_order_id.type", "=", "inbound"),
            ], limit=1)
            if existing_sunrise_pallet_no:
                raise ValidationError(
                    _('Sunrise Pallet No "%s" already exists in inbound order "%s".')
                    % (rec.sunrise_pallet_no,existing_sunrise_pallet_no.inbound_order_id.billno or existing_sunrise_pallet_no.inbound_order_id.reference,))

    def unlink(self):
        for rec in self:
            if rec.inbound_order_product_pallet_ids:
                rec.inbound_order_product_pallet_ids.unlink()
        return super().unlink()


class InboundOrderProductsPallet(models.Model):
    _inherit = "world.depot.inbound.order.products.pallet"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    product_ean = fields.Char(string="Product EAN", copy=False, index=True)
    is_lot = fields.Selection([("N", "No"), ("Y", "Yes")], string="Is Lot", default="Y", copy=False, index=True)
    lot_name = fields.Char(string="Lot Name", copy=False, index=True)

    cprojectid = fields.Char(string="Contract No", copy=False, index=True)
    ndiscounttaxtype = fields.Char(string="Tax Deduction Type", copy=False, index=True)
    vsourcebillcode = fields.Char(string="Source Bill Code", copy=False, index=True)
    vsourcerowno = fields.Char(string="Source Row No", copy=False, index=True)
    box_type = fields.Selection([("full", "Full"), ("partial", "Partial")], string="Box Type", copy=False, index=True)
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
