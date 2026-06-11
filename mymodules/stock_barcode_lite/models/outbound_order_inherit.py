from odoo import _, api, fields, models
from odoo.http import request
from odoo.exceptions import UserError, ValidationError

from odoo.tools.float_utils import float_compare

class OutboundOrderInherit(models.Model):
    _inherit = "world.depot.outbound.order"
    _order = "id desc"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    time_slot = fields.Char(string='Expected harvest time period')  # 预计收货时间段
    cwarehouseid = fields.Char(string="U8C Warehouse ID", copy=False, index=True)
    csalereceiveid = fields.Char(string="Sale Receive ID", copy=False)

    def action_open_outbound_product_import_wizard(self):
        for rec in self:
            if rec.state != "new":
                raise UserError(_("Only new outbound orders can import products."))
            if rec.outbound_order_product_ids:
                raise UserError(_("This outbound order already has pallet/product lines."))
            return {
                "type": "ir.actions.act_window",
                "name": _("Import Products"),
                "res_model": "outbound.product.import.wizard",
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "new",
                "context": {
                    "default_outbound_order_id": rec.id,
                    "default_reference": rec.reference,
                },
            }
        return False

    def validate_sunrise_outgoing_stock_picking(self):
        picking_model = self.env["stock.picking"]
        package_model = self.env["stock.quant.package"]
        quant_model = self.env["stock.quant"]
        lot_model = self.env["stock.lot"]

        for rec in self:
            if rec.project.name != "SUNRISE":
                raise UserError(_("Only SUNRISE projects can create a picking."))
            if rec.state != "confirm":
                raise UserError(_("Only confirmed outbound orders can create a picking."))
            if not rec.pick_type:
                raise UserError(_("The pick type field is required."))
            if rec.pick_type.code not in ("outgoing"):
                raise UserError(_("Please select an outgoing pick type."))
            if not rec.reference:
                raise UserError(_("The reference field is required."))
            if not rec.outbound_order_product_ids:
                raise UserError(_("Please add outbound product lines."))

            existing_picking = picking_model.sudo().search([
                ("outbound_order_id", "=", rec.id),
                ("state", "!=", "cancel"),
            ], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this outbound order."))

            package_mode_map = {}
            demand_map = {}

            for line in rec.outbound_order_product_ids:
                if not line.product_id:
                    raise UserError(_("Product is required on outbound product lines."))
                if not line.sunrise_pallet_no:
                    raise UserError(
                        _('Sunrise pallet number is required for product "%s".')
                        % line.product_id.display_name
                    )
                if line.quantity <= 0:
                    raise UserError(
                        _('Quantity must be greater than 0 for product "%s".')
                        % line.product_id.display_name
                    )
                if line.product_id.tracking == "serial":
                    raise UserError(
                        _('Serial-tracked product "%s" is not supported by Sunrise outgoing picking.')
                        % line.product_id.display_name
                    )
                if line.de_palletize not in ("N", "Y"):
                    raise UserError(
                        _('de_palletize must be N or Y for product "%s".')
                        % line.product_id.display_name
                    )

                package_list = package_model.sudo().search([
                    "|",
                    ("name", "=", line.sunrise_pallet_no),
                    ("barcode", "=", line.sunrise_pallet_no),
                ], limit=2)
                if not package_list:
                    raise UserError(
                        _('Pallet "%s" does not exist in stock package.')
                        % line.sunrise_pallet_no
                    )
                if len(package_list) > 1:
                    raise UserError(
                        _('Pallet "%s" matched multiple stock packages.')
                        % line.sunrise_pallet_no
                    )
                package = package_list[:1]

                lot = False
                if line.is_lot == "Y":
                    if line.product_id.tracking != "lot":
                        raise UserError(
                            _('Product "%s" must enable lot tracking.')
                            % line.product_id.display_name
                        )
                    if not line.lot_name:
                        raise UserError(
                            _('Lot number is required for product "%s".')
                            % line.product_id.display_name
                        )
                    lot = lot_model.sudo().search([
                        ("name", "=", line.lot_name),
                        ("product_id", "=", line.product_id.id),
                    ], limit=1)
                    if not lot:
                        raise UserError(
                            _('Lot "%s" does not exist for product "%s".')
                            % (line.lot_name, line.product_id.display_name)
                        )
                elif line.product_id.tracking == "lot":
                    raise UserError(
                        _('Product "%s" enables lot tracking, so is_lot must be Y.')
                        % line.product_id.display_name
                    )

                if package.id in package_mode_map and package_mode_map[package.id] != line.de_palletize:
                    raise UserError(
                        _('Pallet "%s" cannot mix de_palletize=N and de_palletize=Y.')
                        % line.sunrise_pallet_no
                    )
                package_mode_map[package.id] = line.de_palletize

                demand_key = (package.id, line.product_id.id, lot.id if lot else False)
                demand_map[demand_key] = demand_map.get(demand_key, 0.0) + line.quantity

            for demand_key, demand_qty in demand_map.items():
                package_id, product_id, lot_id = demand_key
                product = self.env["product.product"].sudo().browse(product_id)

                quant_domain = [
                    ("package_id", "=", package_id),
                    ("product_id", "=", product_id),
                    ("location_id.usage", "=", "internal"),
                ]
                if lot_id:
                    quant_domain.append(("lot_id", "=", lot_id))

                quant_list = quant_model.sudo().search(quant_domain)
                available_qty = 0.0
                for quant in quant_list:
                    available_qty += max(quant.quantity - quant.reserved_quantity, 0.0)

                if float_compare(available_qty, demand_qty, precision_rounding=product.uom_id.rounding) < 0:
                    raise UserError(
                        _('Insufficient stock in pallet "%s" for product "%s". Required: %s, Available: %s')
                        % (
                            quant_list[:1].package_id.name if quant_list else package_id,
                            product.display_name,
                            demand_qty,
                            available_qty,
                        )
                    )

            # for package_id, mode in package_mode_map.items():
            #     if mode != "N":
            #         continue
            #
            #     package_quant_list = quant_model.sudo().search([
            #         ("package_id", "=", package_id),
            #         ("location_id.usage", "=", "internal"),
            #     ])
            #
            #     package_available_map = {}
            #     for quant in package_quant_list:
            #         available_qty = max(quant.quantity - quant.reserved_quantity, 0.0)
            #         if float_compare(available_qty, 0.0, precision_rounding=quant.product_id.uom_id.rounding) <= 0:
            #             continue
            #         key = (quant.product_id.id, quant.lot_id.id if quant.lot_id else False)
            #         package_available_map[key] = package_available_map.get(key, 0.0) + available_qty
            #
            #     order_available_map = {}
            #     for demand_key, demand_qty in demand_map.items():
            #         demand_package_id, product_id, lot_id = demand_key
            #         if demand_package_id != package_id:
            #             continue
            #         key = (product_id, lot_id)
            #         order_available_map[key] = order_available_map.get(key, 0.0) + demand_qty
            #
            #     if set(package_available_map.keys()) != set(order_available_map.keys()):
            #         package = package_model.sudo().browse(package_id)
            #         raise UserError(
            #             _('Pallet "%s" is full-pallet outbound, so all stock on the pallet must be included.')
            #             % (package.name or package.barcode)
            #         )
            #
            #     for key, available_qty in package_available_map.items():
            #         product_id, lot_id = key
            #         product = self.env["product.product"].sudo().browse(product_id)
            #         demand_qty = order_available_map.get(key, 0.0)
            #         if float_compare(available_qty, demand_qty, precision_rounding=product.uom_id.rounding) != 0:
            #             package = package_model.sudo().browse(package_id)
            #             raise UserError(
            #                 _('Pallet "%s" is full-pallet outbound. Product "%s" quantity must equal pallet stock. Required: %s, Pallet Stock: %s')
            #                 % (package.name or package.barcode, product.display_name, demand_qty, available_qty)
            #             )

        return True

    def action_sunrise_create_outgoing_stock_picking(self):
        self.validate_sunrise_outgoing_stock_picking()

        picking_model = self.env["stock.picking"]
        group_model = self.env["procurement.group"]
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        package_model = self.env["stock.quant.package"]
        lot_model = self.env["stock.lot"]
        quant_model = self.env["stock.quant"]

        for rec in self:
            with self.env.cr.savepoint():
                group = group_model.sudo().search([("name", "=", rec.billno)], limit=1)
                if not group:
                    group = group_model.create({"name": rec.billno})

                picking = picking_model.create({
                    "picking_type_id": rec.pick_type.id,
                    "location_id": rec.pick_type.default_location_src_id.id,
                    "location_dest_id": rec.pick_type.default_location_dest_id.id,
                    "origin": rec.billno,
                    "partner_id": rec.unload_company.id,
                    "outbound_order_id": rec.id,
                    "scheduled_date": rec.p_date,
                    "planning_date": rec.p_date,
                    "ref_1": rec.reference,
                    "load_ref": rec.load_ref,
                    "group_id": group.id,
                    "owner_id": rec.owner.id if rec.owner else False,
                })

                pool_map = {}
                line_meta_map = {}

                for line in rec.outbound_order_product_ids:
                    package = package_model.sudo().search([
                        "|",
                        ("name", "=", line.sunrise_pallet_no),
                        ("barcode", "=", line.sunrise_pallet_no),
                    ], limit=1)

                    lot = False
                    if line.is_lot == "Y":
                        lot = lot_model.sudo().search([
                            ("name", "=", line.lot_name),
                            ("product_id", "=", line.product_id.id),
                        ], limit=1)

                    pool_key = (package.id, line.product_id.id, lot.id if lot else False)
                    if pool_key not in pool_map:
                        quant_domain = [
                            ("package_id", "=", package.id),
                            ("product_id", "=", line.product_id.id),
                            ("location_id.usage", "=", "internal"),
                        ]
                        if lot:
                            quant_domain.append(("lot_id", "=", lot.id))

                        quant_list = quant_model.sudo().search(quant_domain, order="in_date asc, id asc")
                        bucket_list = []
                        for quant in quant_list:
                            available_qty = max(quant.quantity - quant.reserved_quantity, 0.0)
                            if float_compare(available_qty, 0.0,
                                             precision_rounding=line.product_id.uom_id.rounding) <= 0:
                                continue
                            bucket_list.append({
                                "location_id": quant.location_id,
                                "owner_id": quant.owner_id,
                                "lot_id": quant.lot_id,
                                "remaining_qty": available_qty,
                            })
                        pool_map[pool_key] = bucket_list

                    line_meta_map[line.id] = {
                        "package": package,
                        "lot": lot,
                        "pool_key": pool_key,
                    }

                move_map = {}
                created_moves = self.env["stock.move"]

                for line in rec.outbound_order_product_ids:
                    move = move_model.create({
                        "name": line.product_id.display_name,
                        "product_id": line.product_id.id,
                        "product_uom_qty": line.quantity,
                        "product_uom": line.product_id.uom_id.id,
                        "picking_id": picking.id,
                        "location_id": picking.location_id.id,
                        "location_dest_id": picking.location_dest_id.id,
                        "outbound_order_product_id": line.id,
                        "group_id": group.id,
                    })
                    created_moves |= move
                    move_map[line.id] = move

                # if created_moves:
                #     created_moves._action_confirm(merge=False)

                for line in rec.outbound_order_product_ids:
                    move = move_map[line.id]
                    meta = line_meta_map[line.id]
                    package = meta["package"]
                    lot = meta["lot"]
                    pool_key = meta["pool_key"]
                    bucket_list = pool_map.get(pool_key, [])

                    remaining_qty = line.quantity
                    location_name_list = []

                    for bucket in bucket_list:
                        if float_compare(remaining_qty, 0.0, precision_rounding=line.product_id.uom_id.rounding) <= 0:
                            break
                        if float_compare(bucket["remaining_qty"], 0.0,
                                         precision_rounding=line.product_id.uom_id.rounding) <= 0:
                            continue

                        take_qty = min(bucket["remaining_qty"], remaining_qty)

                        move_line_model.create({
                            "picking_id": picking.id,
                            "move_id": move.id,
                            "product_id": line.product_id.id,
                            "product_uom_id": line.product_id.uom_id.id,
                            "quantity": take_qty,
                            "location_id": bucket["location_id"].id,
                            "location_dest_id": picking.location_dest_id.id,
                            "package_id": package.id,
                            "result_package_id": False,
                            "lot_id": lot.id if lot else (bucket["lot_id"].id if bucket["lot_id"] else False),
                            "owner_id": bucket["owner_id"].id if bucket["owner_id"] else False,
                        })

                        bucket["remaining_qty"] -= take_qty
                        remaining_qty -= take_qty

                        if bucket["location_id"].complete_name and bucket[
                            "location_id"].complete_name not in location_name_list:
                            location_name_list.append(bucket["location_id"].complete_name)

                    if float_compare(remaining_qty, 0.0, precision_rounding=line.product_id.uom_id.rounding) > 0:
                        raise UserError(
                            _('Insufficient stock while creating picking for product "%s". Shortfall: %s')
                            % (line.product_id.display_name, remaining_qty)
                        )

                    if "locations" in line._fields and location_name_list:
                        line.write({"locations": ", ".join(location_name_list)})
                if created_moves:
                    created_moves.invalidate_recordset(["move_line_ids", "quantity", "state"])
                    created_moves._action_confirm(merge=False)
                    created_moves.invalidate_recordset(["move_line_ids", "quantity", "state"])
                    created_moves._recompute_state()

                rec.write({
                    "picking_PICK": picking.id,
                    "picking_Out":  picking.id,
                    "status": "outbound",
                })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Sunrise outbound picking created successfully."),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "name": _("Outbound Order"),
                    "res_model": "world.depot.outbound.order",
                    "res_id": self[:1].id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "target": "current",
                },
            },
        }




class InboundOrderProduct(models.Model):
    _inherit = "world.depot.outbound.order.product"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")],
                                       string="Creation Source", default="manual", readonly=True, copy=False)
    sunrise_pallet_no = fields.Char(string="Sunrise Pallet No", copy=False, index=True)
    product_ean = fields.Char(string="Product EAN", copy=False, index=True)

    de_palletize = fields.Selection([("N", "Full Pallet Outbound"), ("Y", "Depalletize Outbound")],
                                    string="Depalletize", default="N", copy=False, index=True)
    is_lot = fields.Selection([("N", "No"), ("Y", "Yes")], string="Is Lot", default="N", copy=False, index=True)
    lot_name = fields.Char(string="Lot Name", copy=False, index=True)
    m_date = fields.Date(string="Manufacture Date", copy=False)
    e_date = fields.Date(string="Expiration Date", copy=False)
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
    cspaceid = fields.Char(string="Location Code", copy=False, index=True)#货位号


    @api.constrains("outbound_order_id", "pallet_no")
    def check_pallet_no_unique_by_project(self):
        pallet_model = self.env["world.depot.outbound.order.product"]
        for rec in self:
            if not rec.pallet_no or not rec.outbound_order_id or rec.outbound_order_id.state == "cancel":
                continue
            domain = [
                ("id", "!=", rec.id),
                ("pallet_no", "=", rec.pallet_no),
                ("outbound_order_id", "!=", rec.outbound_order_id.id),
                ("outbound_order_id.project", "=", rec.outbound_order_id.project.id),
                ("outbound_order_id.state", "!=", "cancel"),
            ]
            existing = pallet_model.sudo().search(domain, limit=1)
            if existing:
                raise ValidationError(
                    _('Pallet No "%s" already exists in outbound order "%s" for this project.')
                    % (rec.pallet_no, existing.outbound_order_id.billno or existing.outbound_order_id.reference)
                )
