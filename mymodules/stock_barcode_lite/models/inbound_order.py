# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.http import request
from odoo.exceptions import UserError, ValidationError

class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"
    _order = "id desc"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)



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
            existing_package = package_model.sudo().search([
                "|",
                ("name", "in", list(package_names)),
                ("barcode", "in", list(package_names)),
            ], limit=1)

            if existing_package:
                raise UserError(
                    _('Pallet No "%s" already exists as a package.')
                    % (existing_package.name or existing_package.barcode))
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
            },
        }


class InboundOrderProduct(models.Model):
    _inherit = "world.depot.inbound.order.product"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    sunrise_pallet_no = fields.Char(string="Sunrise Pallet No", copy=False, index=True)
    package_id = fields.Many2one('stock.quant.package', string='Pallet', index=True)


    @api.constrains("sunrise_pallet_no")
    def check_sunrise_pallet_no_unique(self):
        pallet_model = self.env["world.depot.inbound.order.product"]
        for rec in self:
            if not rec.sunrise_pallet_no or not rec.inbound_order_id or rec.inbound_order_id.state == "cancel":
                continue
            domain = [
                ("id", "!=", rec.id),
                ("sunrise_pallet_no", "=", rec.sunrise_pallet_no),
                ("inbound_order_id.state", "!=", "cancel"),
            ]
            existing = pallet_model.sudo().search(domain, limit=1)
            if existing:
                raise ValidationError(
                    _('Sunrise Pallet No "%s" already exists in inbound order "%s".')
                    % (rec.sunrise_pallet_no, existing.inbound_order_id.billno or existing.inbound_order_id.reference)
                )

    def unlink(self):
        for rec in self:
            if rec.inbound_order_product_pallet_ids:
                rec.inbound_order_product_pallet_ids.unlink()
        return super().unlink()


class InboundOrderProductsPallet(models.Model):
    _inherit = "world.depot.inbound.order.products.pallet"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    product_ean = fields.Char(string="Product EAN", copy=False, index=True)
    is_lot = fields.Selection([("N", "No"), ("Y", "Yes")], string="Is Lot", default="N", copy=False, index=True)
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
