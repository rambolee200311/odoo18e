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

    def action_main_create_incoming_stock_picking(self):
        for record in self:
            if record.project.name != "DAQING":
                raise UserError(_("Only qd projects can create a picking."))

            if record.state != "confirm":
                raise UserError(_("Only confirmed records can create a picking."))

            if not record.reference:
                raise UserError(_("The reference field is required."))

            if not record.pick_type:
                raise UserError(_("The pick type field is required."))

            if not record.cntr_no:
                raise UserError(_("The container number field is required."))
            if not record.inbound_order_product_ids:
                raise UserError(_("Please add pallet lines."))

            if not record.inbound_order_product_ids.mapped("inbound_order_product_pallet_ids"):
                raise UserError(_("Please add product lines."))
            missing_pallet_lines = record.inbound_order_product_ids.filtered(lambda line: not line.pallet_no)
            if missing_pallet_lines:
                raise UserError(_("The pallet number field is required."))

            existing_picking = self.env["stock.picking"].sudo().search([
                ("inbound_order_id", "=", record.id),
                ("state", "!=", "cancel"),
            ], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this record."))
            if record.pick_type.id == False:
                raise UserError(_("Please select a pick type."))
            if record.pick_type.code != "incoming":
                raise UserError(_("Please select an incoming pick type."))
            picking = self.env["stock.picking"].create({
                "picking_type_id": record.pick_type.id,
                "location_id": record.pick_type.default_location_src_id.id,
                "location_dest_id": record.pick_type.default_location_dest_id.id,
                "origin": record.billno,
                "inbound_order_id": record.id,
                "partner_id": record.owner.id,
                "scheduled_date": record.a_date,
                'bill_of_lading': record.bl_no,
                'cntrno': record.cntr_no,
                "ref_1": record.reference,
                "planning_date": record.date,
                "owner_id": record.owner.id,
            })

            pallet_index = 1
            product_move_map = {}
            for product in record.inbound_order_product_ids:
                for pallet in product.inbound_order_product_pallet_ids:
                    product_id = pallet.product_id.id
                    if product_id not in product_move_map:
                        product_move_map[product_id] = {
                            "product": pallet.product_id,
                            "total_quantity": 0,
                        }
                    product_move_map[product_id]["total_quantity"] += pallet.quantity * product.pallets

            product_moves = {}
            for product_id, product_data in product_move_map.items():
                product = product_data["product"]
                total_quantity = product_data["total_quantity"]
                move = self.env["stock.move"].create({
                    "name": product.name,
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom_qty": total_quantity,
                    "product_uom": product.uom_id.id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                })
                product_moves[product_id] = move

            package_model = self.env["stock.quant.package"]
            lot_model = self.env["stock.lot"]
            for product in record.inbound_order_product_ids:
                if product.pallet_no and int(product.pallets) != 1:
                    raise UserError(_("When pallet number is provided, pallets must be 1."))

                if product.pallet_no:
                    package_name = product.pallet_no
                    existing_package = package_model.sudo().search([("name", "=", package_name)], limit=1)
                    if existing_package:
                        raise UserError(_('Pallet No "%s" already exists as a package.') % package_name)

                    package = package_model.create({
                        "name": package_name,
                        "package_use": "disposable",
                        "billno": record.billno,
                        "reference": record.reference,
                        "cntr_no": record.cntr_no,
                        "barcode": package_name,
                    })
                else:
                    raise UserError(_("Pallet number is required."))

                for pallet in product.inbound_order_product_pallet_ids:
                    move = product_moves[pallet.product_id.id]
                    lot = False
                    if pallet.product_id.tracking == "lot":
                        lot_name = f"{record.a_date.strftime('%Y%m')}-{record.cntr_no}-{str(pallet_index).zfill(4)}"
                        lot = lot_model.sudo().search([
                            ("name", "=", lot_name),
                            ("product_id", "=", pallet.product_id.id),
                        ], limit=1)
                        if not lot:
                            lot = lot_model.create({
                                "name": lot_name,
                                "product_id": pallet.product_id.id,
                            })

                    if pallet.product_id.tracking == "serial" and record.is_scan_sn:
                        for i in range(int(pallet.quantity)):
                            self.env["stock.move.line"].create({
                                "picking_id": picking.id,
                                "move_id": move.id,
                                "product_id": pallet.product_id.id,
                                "product_uom_id": pallet.product_id.uom_id.id,
                                "quantity": 1,
                                "location_id": picking.location_id.id,
                                "location_dest_id": picking.location_dest_id.id,
                                "result_package_id": package.id if record.project.charge_of_pallet else False,
                                "lot_name": "",
                            })
                    else:
                        self.env["stock.move.line"].create({
                            "picking_id": picking.id,
                            "move_id": move.id,
                            "product_id": pallet.product_id.id,
                            "product_uom_id": pallet.product_id.uom_id.id,
                            "quantity": pallet.quantity,
                            "location_id": picking.location_id.id,
                            "location_dest_id": picking.location_dest_id.id,
                            "result_package_id": package.id if record.project.charge_of_pallet else False,
                            "lot_id": lot.id if lot else False,
                        })

                pallet_index += 1

            record.stock_picking_id = picking.id

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

    @api.constrains("inbound_order_id", "pallet_no")
    def check_pallet_no_unique_by_project(self):
        pallet_model = self.env["world.depot.inbound.order.product"]
        for rec in self:
            if not rec.pallet_no or not rec.inbound_order_id or rec.inbound_order_id.state == "cancel":
                continue
            domain = [
                ("id", "!=", rec.id),
                ("pallet_no", "=", rec.pallet_no),
                ("inbound_order_id.project", "=", rec.inbound_order_id.project.id),
                ("inbound_order_id.state", "!=", "cancel"),
            ]
            existing = pallet_model.sudo().search(domain, limit=1)
            if existing:
                raise ValidationError(
                    _('Pallet No "%s" already exists in inbound order "%s" for this project.')
                    % (rec.pallet_no, existing.inbound_order_id.billno or existing.inbound_order_id.reference)
                )

    def unlink(self):
        for rec in self:
            if rec.inbound_order_product_pallet_ids:
                rec.inbound_order_product_pallet_ids.unlink()
        return super().unlink()


class InboundOrderProductsPallet(models.Model):
    _inherit = "world.depot.inbound.order.products.pallet"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    is_lot = fields.Selection([("N", "No"), ("Y", "Yes")], string="Is Lot", default="N", copy=False, index=True)
    lot_name = fields.Char(string="Lot Name", copy=False, index=True)