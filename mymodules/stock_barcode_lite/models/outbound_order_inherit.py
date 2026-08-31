import math

from psycopg2 import sql

from odoo import _, fields, models, api
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

class OutboundOrderInherit(models.Model):
    _inherit = "world.depot.outbound.order"
    _order = "id desc"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
    time_slot = fields.Char(string='Expected harvest time period')  # 预计收货时间段
    cwarehouseid = fields.Char(string="U8C Warehouse ID", copy=False, index=True)
    vsourcebillcode = fields.Char(string="Source Bill Code", copy=False, index=True, tracking=True)
    ccustomerid = fields.Char(string="U8C Customer ID", copy=False)
    u8c_delivery_method = fields.Selection([("pickup", "Pickup"), ("wd", "WD Transport")], string="U8C Delivery Method", copy=False, tracking=True)
    transport_cost_reference = fields.Char(string="Transport Cost Reference", copy=False)
    transport_cost = fields.Float(string="Transport Cost", default=0.0, copy=False)

    whole_pallet_picking_id = fields.Many2one("stock.picking", string="Whole Pallet Picking",copy=False,index=True)
    partial_pallet_picking_id = fields.Many2one("stock.picking", string="Partial Pallet Picking",copy=False, index=True)
    outgoing_picking_lines = fields.One2many("stock.picking", "outbound_order_id", string="Outgoing Pickings", tracking=True)
    sunrise_pallet_count = fields.Integer(string="Sunrise Pallet Count", compute="_compute_sunrise_pallet_count",
                                          store=True)
    eta = fields.Date(string='ETA', tracking=True)
    organic = fields.Boolean(string="Organic", compute="_compute_organic", store=True, copy=False, index=True)
    new_pallet_count_total = fields.Integer(string="New Pallet Count Total", compute="_compute_new_pallet_count_total",
                                            store=True, readonly=True, copy=False)
    consignee_id = fields.Many2one("res.partner", string="Consignee", copy=False, index=True)

    @api.depends(
        "outgoing_picking_lines",
        "outgoing_picking_lines.new_pallet_count",
        "outgoing_picking_lines.picking_type_id.code",
        "outgoing_picking_lines.state",
    )
    def _compute_new_pallet_count_total(self):
        for rec in self:
            rec.new_pallet_count_total = sum(
                picking.new_pallet_count
                for picking in rec.outgoing_picking_lines
                if picking.picking_type_id.code == "outgoing" and picking.state != "cancel"
            )
    @api.onchange("project")
    def onchange_project_warehouse(self):
        for record in self:
            record.warehouse = record.project.warehouse
            record.pick_type = record.project.outbound_pick_type


    @api.depends("outbound_order_product_ids.package_id")
    def _compute_sunrise_pallet_count(self):
        for rec in self:
            rec.sunrise_pallet_count = len(rec.outbound_order_product_ids.mapped("package_id"))

    def action_confirm(self):
        for rec in self:
            if rec.project.name == "SUNRISE":
                rec.validate_sunrise_outbound_confirm_values()
        return super().action_confirm()

    @api.depends("outbound_order_product_ids.product_id.product_tmpl_id.organic")
    def _compute_organic(self):
        for rec in self:
            rec.organic = any(rec.outbound_order_product_ids.mapped("product_id.product_tmpl_id.organic"))

    def validate_sunrise_outbound_confirm_values(self):
        for rec in self:
            if rec.project.name != "SUNRISE":
                continue

            missing_fields = []
            if not rec.p_date:
                missing_fields.append(rec._fields["p_date"].string)
            if not rec.vsourcebillcode:
                missing_fields.append(rec._fields["vsourcebillcode"].string)
            if not rec.cwarehouseid:
                missing_fields.append(rec._fields["cwarehouseid"].string)
            if not rec.ccustomerid:
                missing_fields.append(rec._fields["ccustomerid"].string)
            if not rec.u8c_delivery_method:
                missing_fields.append(rec._fields["u8c_delivery_method"].string)
            if rec.u8c_delivery_method == "pickup" and not rec.load_ref:
                missing_fields.append(rec._fields["load_ref"].string)
            if not rec.unload_company:
                missing_fields.append(rec._fields["unload_company"].string)
            if not rec.consignee_id:
                missing_fields.append(rec._fields["consignee_id"].string)
            if not rec.delivery_street:
                missing_fields.append(rec._fields["delivery_street"].string)
            if not rec.delivery_phone:
                missing_fields.append(rec._fields["delivery_phone"].string)
            if rec.u8c_delivery_method == "pickup" and not rec.time_slot:
                missing_fields.append(rec._fields["time_slot"].string)

            if missing_fields:
                raise UserError(_("Sunrise outbound order %s is missing required fields: %s") % (rec.reference or rec.billno or rec.id, ", ".join(missing_fields)))

            if rec.u8c_delivery_method not in ("pickup", "wd"):
                raise UserError(_("Sunrise outbound order %s u8c_delivery_method must be pickup or wd.") % (rec.reference or rec.billno or rec.id))

            if not rec.outbound_order_product_ids:
                raise UserError(_("Sunrise outbound order %s must have at least one product line.") % (rec.reference or rec.billno or rec.id))

            for line_index, line in enumerate(rec.outbound_order_product_ids, start=1):
                line_name = _("Outbound product line %s") % line_index
                line_missing_fields = []

                if not line.product_id:
                    line_missing_fields.append(line._fields["product_id"].string)
                if line.creation_source in ("api", "import") and not line.source_product_code:
                    line_missing_fields.append(line._fields["source_product_code"].string)
                if not line.pallet_no:
                    line_missing_fields.append(line._fields["pallet_no"].string)
                if not line.package_id:
                    line_missing_fields.append(line._fields["package_id"].string)
                if not line.cprojectid:
                    line_missing_fields.append(line._fields["cprojectid"].string)
                if not line.vsourcebillcode:
                    line_missing_fields.append(line._fields["vsourcebillcode"].string)
                if not line.vsourcerowno:
                    line_missing_fields.append(line._fields["vsourcerowno"].string)
                if not line.cspaceid:
                    line_missing_fields.append(line._fields["cspaceid"].string)
                if not line.box_type:
                    line_missing_fields.append(line._fields["box_type"].string)
                if not line.castunitid:
                    line_missing_fields.append(line._fields["castunitid"].string)
                if not line.u8_aux_uom_name:
                    line_missing_fields.append(line._fields["u8_aux_uom_name"].string)
                if not line.is_lot:
                    line_missing_fields.append(line._fields["is_lot"].string)
                if line.is_lot == "Y" and not line.lot_name:
                    line_missing_fields.append(line._fields["lot_name"].string)

                if line_missing_fields:
                    raise UserError(_("%s is missing required fields: %s") % (line_name, ", ".join(line_missing_fields)))

                if line.vsourcebillcode != rec.vsourcebillcode:
                    raise UserError(_("%s vsourcebillcode must equal outbound order vsourcebillcode.") % line_name)

                if line.box_type not in ("full", "partial"):
                    raise UserError(_("%s box_type must be full or partial.") % line_name)
                if line.box_qty <= 0:
                    raise UserError(_("%s box_qty must be greater than 0.") % line_name)
                if line.box_in_qty <= 0:
                    raise UserError(_("%s box_in_qty must be greater than 0.") % line_name)
                if line.ninnum <= 0:
                    raise UserError(_("%s ninnum must be greater than 0.") % line_name)
                if line.u8_aux_qty <= 0:
                    raise UserError(_("%s u8_aux_qty must be greater than 0.") % line_name)
                if line.u8_conversion_rate <= 0:
                    raise UserError(_("%s u8_conversion_rate must be greater than 0.") % line_name)

                expected_ninnum = line.box_qty * line.box_in_qty
                if not math.isclose(
                        line.ninnum,
                        expected_ninnum,
                        rel_tol=1e-9,
                        abs_tol=1e-6,
                ):
                    raise UserError(_("%s ninnum must equal box_qty * box_in_qty.") % line_name)

                if line.box_type == "full" and not math.isclose(
                        line.box_in_qty,
                        line.u8_conversion_rate,
                        rel_tol=1e-9,
                        abs_tol=1e-6,
                ):
                    raise UserError(
                        _("%s box_in_qty must equal u8_conversion_rate when box_type is full.")
                        % line_name
                    )
                if line.box_type == "partial" and math.isclose(
                        line.box_in_qty,
                        line.u8_conversion_rate,
                        rel_tol=1e-9,
                        abs_tol=1e-6,
                ):
                    raise UserError(
                        _("%s box_in_qty must not equal u8_conversion_rate when box_type is partial.")
                        % line_name
                    )

                line.validate_sunrise_source_product_specifications()



    def action_cancel(self):
        normal_records = self.env["world.depot.outbound.order"]

        for rec in self:
            if rec.project.name not in ("SUNRISE", "HOYMILES"):
                normal_records |= rec
                continue

            if rec.state == "cancel":
                raise UserError(_("This order %s has already been canceled.") % rec.reference)

            picking_list = rec.get_sunrise_outbound_cancel_picking_list()
            done_picking_list = picking_list.filtered(lambda picking: picking.state == "done")
            not_done_picking_list = picking_list - done_picking_list

            if done_picking_list:
                rec.validate_sunrise_outbound_returned_before_cancel(done_picking_list)

            for picking in not_done_picking_list:
                try:
                    picking.unlink()
                except Exception as error:
                    raise UserError(
                        _("Failed to delete stock picking for order %s: %s")
                        % (rec.reference, str(error))
                    )

            rec.write({
                "state": "cancel",
                "whole_pallet_picking_id": False,
                "partial_pallet_picking_id": False,
                "picking_PICK": False ,
                "picking_Out": False,
            })

        if normal_records:
            return super(OutboundOrderInherit, normal_records).action_cancel()

        return True

    def get_sunrise_outbound_cancel_picking_list(self):
        picking_model = self.env["stock.picking"]
        result = picking_model

        for rec in self:
            picking_list = picking_model.sudo().search([
                ("outbound_order_id", "=", rec.id),
                ("state", "!=", "cancel"),
                ("picking_type_id.code", "=", "outgoing"),
                ("return_id", "=", False),
            ], order="id")
            result |= picking_list

        return result

    def validate_sunrise_outbound_returned_before_cancel(self, picking_list):
        move_model = self.env["stock.move"]

        for rec in self:
            for picking in picking_list:
                done_move_list = picking.move_ids_without_package.filtered(
                    lambda move: move.state == "done"
                                 and move.product_id
                                 and move.product_uom_qty > 0
                                 and not move.origin_returned_move_id
                )


                for move in done_move_list:
                    returned_move_list = move_model.sudo().search([
                        ("origin_returned_move_id", "=", move.id),
                        ("state", "=", "done"),
                    ])

                    returned_qty = 0.0
                    for returned_move in returned_move_list:
                        returned_qty += returned_move.product_uom._compute_quantity(
                            returned_move.product_uom_qty,
                            move.product_uom,
                            rounding_method="HALF-UP",
                        )

                    if returned_qty < move.product_uom_qty:
                        raise UserError(
                            _("Outbound order %s has done picking %s. Please return product %s before cancelling. Required return qty: %s, Returned qty: %s")
                            % (
                                rec.reference,
                                picking.name,
                                move.product_id.display_name,
                                move.product_uom_qty,
                                returned_qty,
                            )
                        )
        return True

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
                ("picking_type_id.code", "=", "outgoing"),
                ("return_id", "=", False),
            ], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this outbound order."))

            package_mode_map = {}
            demand_map = {}

            for line in rec.outbound_order_product_ids:
                if not line.product_id:
                    raise UserError(_("Product is required on outbound product lines."))
                if not line.package_id:
                    raise UserError(
                        _('Package is required for product "%s".')
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

                package = line.package_id

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
                        % (package.name or package.barcode)
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

                line_meta_map = {}
                package_demand_map = {}
                package_stock_map = {}
                pool_map = {}

                for line in rec.outbound_order_product_ids:
                    package = line.package_id

                    lot = False
                    if line.is_lot == "Y":
                        lot = lot_model.sudo().search([
                            ("name", "=", line.lot_name),
                            ("product_id", "=", line.product_id.id),
                        ], limit=1)

                    demand_key = (line.product_id.id, lot.id if lot else False)
                    package_demand_map.setdefault(package.id, {})
                    if demand_key not in package_demand_map[package.id]:
                        package_demand_map[package.id][demand_key] = {
                            "product": line.product_id,
                            "quantity": 0.0,
                        }
                    package_demand_map[package.id][demand_key]["quantity"] += line.quantity

                    line_meta_map[line.id] = {
                        "package": package,
                        "lot": lot,
                        "demand_key": demand_key,
                        "pool_key": (package.id, line.product_id.id, lot.id if lot else False),
                    }

                for package_id in package_demand_map:
                    stock_map = {}
                    location_ids = set()
                    quant_list = quant_model.sudo().search([
                        ("package_id", "=", package_id),
                        ("location_id.usage", "=", "internal"),
                        ("quantity", ">", 0),
                    ], order="location_id, product_id, lot_id, in_date asc, id asc")

                    for quant in quant_list:
                        stock_key = (quant.product_id.id, quant.lot_id.id if quant.lot_id else False)
                        if stock_key not in stock_map:
                            stock_map[stock_key] = {
                                "product": quant.product_id,
                                "quantity": 0.0,
                            }
                        stock_map[stock_key]["quantity"] += quant.quantity or 0.0
                        location_ids.add(quant.location_id.id)

                    package_stock_map[package_id] = {
                        "stock_map": stock_map,
                        "location_ids": location_ids,
                    }

                package_mode_map = {}
                for package_id, demand_map in package_demand_map.items():
                    stock_data = package_stock_map.get(package_id, {})
                    stock_map = stock_data.get("stock_map", {})
                    location_ids = stock_data.get("location_ids", set())
                    is_whole_pallet = True

                    if set(stock_map.keys()) != set(demand_map.keys()):
                        is_whole_pallet = False

                    if is_whole_pallet and len(location_ids) > 1:
                        package = package_model.sudo().browse(package_id)
                        raise UserError(_('Pallet "%s" stock is split across multiple locations.') % (package.name or package.barcode))

                    if is_whole_pallet:
                        for stock_key, stock_line in stock_map.items():
                            product = stock_line["product"]
                            demand_qty = demand_map[stock_key]["quantity"]
                            stock_qty = stock_line["quantity"]
                            if float_compare(stock_qty, demand_qty, precision_rounding=product.uom_id.rounding) != 0:
                                is_whole_pallet = False
                                break

                    package_mode_map[package_id] = "whole_pallet" if is_whole_pallet else "partial_pallet"

                for line in rec.outbound_order_product_ids:
                    meta = line_meta_map[line.id]
                    pool_key = meta["pool_key"]
                    if pool_key in pool_map:
                        continue

                    package = meta["package"]
                    lot = meta["lot"]
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
                        available_qty = max((quant.quantity or 0.0) - (quant.reserved_quantity or 0.0), 0.0)
                        if float_compare(available_qty, 0.0, precision_rounding=line.product_id.uom_id.rounding) <= 0:
                            continue
                        bucket_list.append({
                            "location_id": quant.location_id,
                            "owner_id": quant.owner_id,
                            "lot_id": quant.lot_id,
                            "remaining_qty": available_qty,
                        })
                    pool_map[pool_key] = bucket_list

                picking_map = {}
                for scan_mode in ("whole_pallet", "partial_pallet"):
                    mode_lines = rec.outbound_order_product_ids.filtered(
                        lambda line: package_mode_map.get(line_meta_map[line.id]["package"].id) == scan_mode
                    )
                    if not mode_lines:
                        continue

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
                        "outbound_scan_mode": scan_mode,
                        "project_id": rec.project.id if rec.project else False,
                    })
                    picking_map[scan_mode] = picking

                    move_map = {}
                    created_moves = self.env["stock.move"]

                    for line in mode_lines:
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

                    for line in mode_lines:
                        move = move_map[line.id]
                        meta = line_meta_map[line.id]
                        package = meta["package"]
                        lot = meta["lot"]
                        bucket_list = pool_map.get(meta["pool_key"], [])

                        remaining_qty = line.quantity
                        location_name_list = []

                        for bucket in bucket_list:
                            if float_compare(remaining_qty, 0.0, precision_rounding=line.product_id.uom_id.rounding) <= 0:
                                break
                            if float_compare(bucket["remaining_qty"], 0.0, precision_rounding=line.product_id.uom_id.rounding) <= 0:
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

                            if bucket["location_id"].complete_name and bucket["location_id"].complete_name not in location_name_list:
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

                whole_picking = picking_map.get("whole_pallet")
                partial_picking = picking_map.get("partial_pallet")
                first_picking = whole_picking or partial_picking

                rec.write({
                    "whole_pallet_picking_id": whole_picking.id if whole_picking else False,
                    "partial_pallet_picking_id": partial_picking.id if partial_picking else False,
                    "picking_PICK": whole_picking.id if whole_picking else first_picking.id,
                    "picking_Out": partial_picking.id if partial_picking else first_picking.id,
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




    def action_sunrise_create_outgoing_stock_picking_total(self):
        self.validate_sunrise_outgoing_stock_picking()

        picking_model = self.env["stock.picking"]
        group_model = self.env["procurement.group"]
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
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
                    package = line.package_id

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




class OutboundOrderProduct(models.Model):
    _inherit = "world.depot.outbound.order.product"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")],
                                       string="Creation Source", default="manual", readonly=True, copy=False)
    package_id = fields.Many2one(
        "stock.quant.package",
        string="Package",
        copy=False,
        index=True,
        tracking=True,
        ondelete="restrict",
    )
    package_barcode = fields.Char(related="package_id.barcode", string="Package Barcode", readonly=True)
    source_product_code = fields.Char(string="Source Product Code", copy=False, index=True, tracking=True)
    product_ean = fields.Char(string="Product EAN", copy=False, index=True)

    de_palletize = fields.Selection([("N", "Full Pallet Outbound"), ("Y", "Depalletize Outbound")],
                                    string="Depalletize", default="Y", copy=False, index=True)
    is_lot = fields.Selection([("N", "No"), ("Y", "Yes")], string="Is Lot", default="N", copy=False, index=True)
    lot_name = fields.Char(string="Lot Name", copy=False, index=True, tracking=True)
    m_date = fields.Date(string="Manufacture Date", copy=False)
    e_date = fields.Date(string="Expiration Date", copy=False)
    cprojectid = fields.Char(string="Sunrise Ref", copy=False, index=True)
    ndiscounttaxtype = fields.Char(string="Tax Deduction Type", copy=False, index=True, tracking=True)
    vsourcebillcode = fields.Char(string="Source Bill Code", copy=False, index=True)
    vsourcerowno = fields.Char(string="Source Row No", copy=False, index=True, tracking=True)
    box_type = fields.Selection([("full", "Full"), ("partial", "Non-standard")], string="Box Type", copy=False, index=True)
    box_qty = fields.Integer(string="Box Qty", copy=False, tracking=True)
    ninnum = fields.Float(string="Received Units", copy=False, tracking=True)
    box_in_qty = fields.Float(string="Box In Qty", copy=False, tracking=True)
    u8_aux_qty = fields.Float(string="U8 Aux Qty", copy=False)
    u8_conversion_rate = fields.Float(string="U8 Conversion Rate", copy=False)
    castunitid = fields.Char(string="Assistant Unit", copy=False, index=True)
    u8_aux_uom_name = fields.Char(string="U8 Aux UOM Name", copy=False, index=True)
    cspaceid = fields.Char(string="Location Code", copy=False, index=True, tracking=True)#货位号
    gross_weight = fields.Char(string="Gross Weight(kg)", copy=False)
    pallet_dimensions = fields.Char(string="Carton Dimensions(m)", copy=False)

    @api.onchange("package_id", "product_id", "is_lot", "lot_name")
    def onchange_sunrise_source_product_specifications(self):
        inbound_detail_model = self.env["world.depot.inbound.order.products.pallet"].sudo()

        for rec in self:
            project = rec.outbound_order_id.project or rec.project
            if project.name != "SUNRISE":
                continue

            rec.gross_weight = False
            rec.pallet_dimensions = False

            if not rec.package_id or not rec.product_id or not rec.is_lot:
                continue
            if rec.is_lot == "Y" and not rec.lot_name:
                continue

            source_domain = [
                ("inbound_order_product_id.package_id", "=", rec.package_id.id),
                ("inbound_order_product_id.inbound_order_id.project", "=", project.id),
                ("inbound_order_product_id.inbound_order_id.state", "!=", "cancel"),
                ("product_id", "=", rec.product_id.id),
                ("is_lot", "=", rec.is_lot),
            ]
            if rec.is_lot == "Y":
                source_domain.append(("lot_name", "=", rec.lot_name))

            source_detail_lines = inbound_detail_model.search(source_domain, order="id")
            if not source_detail_lines:
                continue

            source_specification = source_detail_lines.get_sunrise_product_specification(allow_missing=True)
            if source_specification.get("has_specification"):
                rec.gross_weight = source_specification["gross_weight"]
                rec.pallet_dimensions = source_specification["pallet_dimensions"]

    def validate_sunrise_source_product_specifications(self):
        inbound_detail_model = self.env["world.depot.inbound.order.products.pallet"].sudo()
        for rec in self:
            source_domain = [
                ("inbound_order_product_id.package_id", "=", rec.package_id.id),
                ("inbound_order_product_id.inbound_order_id.project", "=", rec.project.id),
                ("inbound_order_product_id.inbound_order_id.state", "!=", "cancel"),
                ("product_id", "=", rec.product_id.id),
                ("is_lot", "=", rec.is_lot),
            ]
            if rec.is_lot == "Y":
                source_domain.append(("lot_name", "=", rec.lot_name))
            source_detail_lines = inbound_detail_model.search(source_domain, order="id")
            if not source_detail_lines:
                raise UserError(
                    _("No inbound source detail was found for product %s, pallet %s and lot %s.")
                    % (rec.product_id.display_name, rec.pallet_no or "-", rec.lot_name or "-")
                )

            source_specification = source_detail_lines.get_sunrise_product_specification(allow_missing=True)
            line_name = _("Product %s, pallet %s, lot %s") % (
                rec.product_id.display_name,
                rec.pallet_no or "-",
                rec.lot_name or "-",
            )

            if not source_specification.get("has_specification"):
                continue

            try:
                gross_weight = float(rec.gross_weight)
            except (TypeError, ValueError) as error:
                raise UserError(_("%s gross weight must be a valid positive number.") % line_name) from error
            if not math.isfinite(gross_weight) or gross_weight <= 0:
                raise UserError(_("%s gross weight must be a valid positive number.") % line_name)

            pallet_dimensions = "".join((rec.pallet_dimensions or "").upper().split())
            if not pallet_dimensions:
                raise UserError(_("%s carton dimensions must not be blank.") % line_name)
            if not math.isclose(
                    gross_weight,
                    source_specification["gross_weight_value"],
                    rel_tol=1e-9,
                    abs_tol=1e-6,
            ) or pallet_dimensions != source_specification["pallet_dimensions_value"]:
                raise UserError(
                    _("%s gross weight and carton dimensions must match the inbound source detail.") % line_name
                )
        return True

    def init(self):
        super().init()
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
                    UPDATE {table} AS outbound_line
                       SET package_id = package.id
                      FROM stock_quant_package AS package
                     WHERE outbound_line.package_id IS NULL
                       AND COALESCE(outbound_line.sunrise_pallet_no, '') <> ''
                       AND package.barcode = outbound_line.sunrise_pallet_no
                """
            ).format(table=sql.Identifier(self._table))
        )

    # @api.constrains("outbound_order_id", "pallet_no")
    # def check_pallet_no_unique_by_project(self):
    #     pallet_model = self.env["world.depot.outbound.order.product"]
    #     for rec in self:
    #         if not rec.pallet_no or not rec.outbound_order_id or rec.outbound_order_id.state == "cancel":
    #             continue
    #         domain = [
    #             ("id", "!=", rec.id),
    #             ("pallet_no", "=", rec.pallet_no),
    #             ("outbound_order_id", "!=", rec.outbound_order_id.id),
    #             ("outbound_order_id.project", "=", rec.outbound_order_id.project.id),
    #             ("outbound_order_id.state", "!=", "cancel"),
    #         ]
    #         existing = pallet_model.sudo().search(domain, limit=1)
    #         if existing:
    #             raise ValidationError(
    #                 _('Pallet No "%s" already exists in outbound order "%s" for this project.')
    #                 % (rec.pallet_no, existing.outbound_order_id.billno or existing.outbound_order_id.reference)
    #             )
