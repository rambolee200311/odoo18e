# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class BlindStockCountWorkPackage(models.Model):
    _inherit = "blind.stock.count.work.package"

    clearance_batch_lines = fields.One2many("blind.stock.count.clearance.batch", "work_package_id", string="Clearance Batches", copy=False)
    outbound_picking_lines = fields.One2many("stock.picking", "blind_stock_count_work_package_id", string="Outbound Pickings", domain=[("is_blind_stock_count_clearance", "=", True)], copy=False)
    cancel_picking_batch_lines = fields.One2many("blind.stock.count.cancel.picking.batch", "work_package_id", string="Cancellation Batches", copy=False)
    clearance_picking_type_id = fields.Many2one("stock.picking.type", string="Clearance Outbound Operation Type", copy=False, index=True, domain=[("code", "=", "outgoing")], tracking=True)
    clearance_destination_location_id = fields.Many2one("stock.location", string="Clearance Destination Location", copy=False, index=True, domain=[("usage", "not in", ["internal", "view"])], tracking=True)
    receipt_picking_type_id = fields.Many2one("stock.picking.type", string="Receipt Inbound Operation Type", copy=False, index=True, domain=[("code", "=", "incoming")], tracking=True)
    receipt_source_location_id = fields.Many2one("stock.location", string="Receipt Source Location", copy=False, index=True, domain=[("usage", "not in", ["internal", "view"])], tracking=True)

    def get_cancelable_pending_pickings(self):
        picking_model = self.env["stock.picking"]
        product_model = self.env["product.product"]
        picking_ids = []
        for rec in self:
            domain = [("picking_type_id.code", "in", ["outgoing", "internal", "incoming"]), ("move_ids.product_id.categ_id", "child_of", rec.category_id.id)]
            pending_pickings = picking_model.sudo().search(domain + [("state", "not in", ["done", "cancel"])], order="id desc")
            inconsistent_done_pickings = picking_model.sudo().search(domain + [("state", "=", "done"), ("move_ids.state", "in", ["draft", "waiting", "confirmed", "partially_available", "assigned"])], order="id desc")
            for picking in pending_pickings | inconsistent_done_pickings:
                active_moves = picking.move_ids.filtered(lambda move: move.state != "cancel")
                allowed_products = product_model.sudo().search([("id", "in", active_moves.product_id.ids), ("categ_id", "child_of", rec.category_id.id)])
                relevant_locations = active_moves.location_dest_id if picking.picking_type_id.code == "incoming" else active_moves.location_id
                if not active_moves or active_moves.filtered(lambda move: move.state == "done") or relevant_locations.filtered(lambda location: location.usage != "internal") or (rec.location_line_ids and relevant_locations.filtered(lambda location: location not in rec.location_line_ids)) or set(active_moves.product_id.ids) != set(allowed_products.ids):
                    continue
                picking_ids.append(picking.id)
        return picking_model.browse(sorted(set(picking_ids), reverse=True))

    def action_open_cancel_pending_picking_list(self):
        picking_model = self.env["stock.picking"]
        pending_picking_list_view = self.env.ref("blind_stock_count.view_blind_stock_count_pending_picking_list")
        for rec in self:
            if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
                raise UserError(_("Only a warehouse manager or system administrator can cancel pending pickings."))
            if rec.state != "done":
                raise UserError(_("Pending pickings can only be cancelled from a completed work package."))
            if picking_model.sudo().search([("blind_stock_count_work_package_id", "=", rec.id), ("is_blind_stock_count_clearance", "=", True), ("state", "not in", ["done", "cancel"])], limit=1):
                raise UserError(_("Pending pickings cannot be cancelled while clearance outbound pickings are still in progress."))
            pickings = rec.get_cancelable_pending_pickings()
            if not pickings:
                raise UserError(_("No pending outbound, internal, or inbound pickings match this work package category and location scope."))
            return {"type": "ir.actions.act_window", "name": _("Pending Pickings"), "res_model": "stock.picking", "view_mode": "list,form", "views": [(pending_picking_list_view.id, "list"), (False, "form")], "domain": [("id", "in", pickings.ids)], "context": {"blind_stock_count_cancel_work_package_id": rec.id, "create": False, "edit": False, "delete": False}, "target": "current"}

    def action_create_clearance(self):
        cancel_picking_batch_line_model = self.env["blind.stock.count.cancel.picking.batch.line"]
        clearance_batch_model = self.env["blind.stock.count.clearance.batch"]
        picking_model = self.env["stock.picking"]
        wizard_model = self.env["blind.stock.count.generate.clearance.batch"]
        if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
            raise UserError(_("Only a warehouse manager or system administrator can generate a clearance order."))
        for rec in self:
            if rec.state != "done":
                raise UserError(_("A clearance order can only be generated from a completed work package."))
            if not rec.clearance_picking_type_id or rec.clearance_picking_type_id.code != "outgoing":
                raise UserError(_("Select a clearance outbound operation type on the work package before generating clearance pickings."))
            if not rec.clearance_destination_location_id:
                raise UserError(_("Select a clearance destination location on the work package before generating clearance pickings."))
            if cancel_picking_batch_line_model.sudo().search_count([("cancel_picking_batch_id.work_package_id", "=", rec.id), ("state", "in", ["queued", "running"])]):
                raise UserError(_("Wait for the queued pending picking cancellations to finish before generating clearance pickings."))
            if clearance_batch_model.sudo().search_count([("work_package_id", "=", rec.id), ("state", "in", ["queued", "running"])]):
                raise UserError(_("A clearance picking generation task is already queued or running for this work package."))
            if picking_model.sudo().search([("blind_stock_count_work_package_id", "=", rec.id), ("is_blind_stock_count_clearance", "=", True), ("state", "!=", "cancel")], limit=1):
                raise UserError(_("An active clearance outbound picking already exists for this work package."))
            wizard = wizard_model.create({"work_package_id": rec.id})
            return {"type": "ir.actions.act_window", "name": _("Generate Clearance Pickings"), "res_model": "blind.stock.count.generate.clearance.batch", "view_mode": "form", "res_id": wizard.id, "target": "new"}

    def action_cancel(self):
        picking_model = self.env["stock.picking"]
        clearance_batch_model = self.env["blind.stock.count.clearance.batch"]
        for rec in self:
            if clearance_batch_model.sudo().search_count([("work_package_id", "=", rec.id), ("state", "in", ["queued", "running"])]):
                raise UserError(_("Wait for the clearance picking generation task before cancelling the work package."))
            if picking_model.sudo().search_count([("blind_stock_count_work_package_id", "=", rec.id), ("is_blind_stock_count_clearance", "=", True), ("state", "!=", "cancel")]) or picking_model.sudo().search_count([("blind_stock_count_work_package_id", "=", rec.id), ("is_blind_stock_count_receipt", "=", True), ("state", "!=", "cancel")]):
                raise UserError(_("Cancel the active clearance or inbound pickings before cancelling the work package."))
        return super().action_cancel()


class BlindStockCountClearanceBatch(models.Model):
    _name = "blind.stock.count.clearance.batch"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count Clearance Batch"
    _order = "id desc"

    name = fields.Char(string="Clearance Batch Number", required=True, readonly=True, copy=False, index=True, default=lambda self: self.env["ir.sequence"].next_by_code("blind.stock.count.clearance.batch") or _("New"))
    work_package_id = fields.Many2one("blind.stock.count.work.package", string="Work Package", required=True, ondelete="restrict", copy=False, index=True, tracking=True)
    category_id = fields.Many2one(related="work_package_id.category_id", string="Product Category", readonly=True)
    location_line_ids = fields.Many2many(related="work_package_id.location_line_ids", string="Location Scope", readonly=True)
    maximum_lines_per_clearance = fields.Integer(string="Maximum Lines per Clearance", required=True, readonly=True, copy=False)
    source_quant_count = fields.Integer(string="Source Quant Count", required=True, readonly=True, copy=False)
    normalized_negative_quant_count = fields.Integer(string="Normalized Negative Quant Count", required=True, readonly=True, copy=False)
    released_orphan_reservation_quant_count = fields.Integer(string="Released Orphan Reservation Quant Count", required=True, readonly=True, copy=False, default=0)
    released_orphan_reservation_quantity = fields.Float(string="Released Orphan Reservation Quantity", required=True, readonly=True, copy=False, default=0.0)
    outbound_picking_lines = fields.One2many("stock.picking", "blind_stock_count_clearance_batch_id", string="Outbound Pickings", copy=False)
    requested_by_id = fields.Many2one("res.users", string="Requested By", required=True, readonly=True, default=lambda self: self.env.user, copy=False, index=True)
    requested_at = fields.Datetime(string="Requested At", required=True, readonly=True, default=fields.Datetime.now, copy=False, index=True)
    state = fields.Selection([("queued", "Queued"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")], string="Status", required=True, readonly=True, default="queued", copy=False, index=True, tracking=True)
    queue_job_id = fields.Many2one("queue.job", string="Queue Job", readonly=True, ondelete="set null", copy=False, index=True)
    error_message = fields.Text(string="Error Message", readonly=True, copy=False)

    def job_generate_outbound_pickings(self):
        move_line_model = self.env["stock.move.line"]
        move_model = self.env["stock.move"]
        picking_model = self.env["stock.picking"]
        quant_model = self.env["stock.quant"]
        for rec in self:
            rec.write({"state": "running", "error_message": False})
            try:
                with self.env.cr.savepoint():
                    if rec.work_package_id.state != "done":
                        raise UserError(_("A clearance picking can only be generated from a completed work package."))
                    if not rec.work_package_id.clearance_picking_type_id or rec.work_package_id.clearance_picking_type_id.code != "outgoing":
                        raise UserError(_("Select a clearance outbound operation type on the work package before generating clearance pickings."))
                    if not rec.work_package_id.clearance_destination_location_id:
                        raise UserError(_("Select a clearance destination location on the work package before generating clearance pickings."))
                    if self.env["blind.stock.count.cancel.picking.batch.line"].sudo().search_count([("cancel_picking_batch_id.work_package_id", "=", rec.work_package_id.id), ("state", "in", ["queued", "running"])]):
                        raise UserError(_("Wait for the queued pending picking cancellations to finish before generating clearance pickings."))
                    if picking_model.sudo().search_count([("blind_stock_count_work_package_id", "=", rec.work_package_id.id), ("is_blind_stock_count_clearance", "=", True), ("state", "!=", "cancel")]):
                        raise UserError(_("An active clearance outbound picking already exists for this work package."))
                    quant_domain = [("location_id.usage", "=", "internal"), ("product_id.categ_id", "child_of", rec.work_package_id.category_id.id)]
                    if rec.work_package_id.location_line_ids:
                        quant_domain.append(("location_id", "in", rec.work_package_id.location_line_ids.ids))
                    reserved_quants = quant_model.sudo()._read_group(quant_domain + [("reserved_quantity", "!=", 0)], ["product_id", "location_id", "lot_id", "package_id", "owner_id"], ["reserved_quantity:sum", "id:recordset"])
                    reservation_move_domain = [("state", "in", ["assigned", "partially_available", "waiting", "confirmed"]), ("quantity_product_uom", "!=", 0), ("product_id.is_storable", "=", True), ("location_id.usage", "=", "internal"), ("product_id.categ_id", "child_of", rec.work_package_id.category_id.id)]
                    if rec.work_package_id.location_line_ids:
                        reservation_move_domain.append(("location_id", "in", rec.work_package_id.location_line_ids.ids))
                    reserved_move_lines = move_line_model.sudo()._read_group(reservation_move_domain, ["product_id", "location_id", "lot_id", "package_id", "owner_id"], ["quantity_product_uom:sum"])
                    reserved_move_quantities = {(product.id, location.id, lot.id if lot else False, package.id if package else False, owner.id if owner else False): reserved_quantity for product, location, lot, package, owner, reserved_quantity in reserved_move_lines}
                    released_orphan_reservation_quant_count = 0
                    released_orphan_reservation_quantity = 0.0
                    for product, location, lot, package, owner, reserved_quantity, quants in reserved_quants:
                        reserved_move_quantity = reserved_move_quantities.get((product.id, location.id, lot.id if lot else False, package.id if package else False, owner.id if owner else False), 0)
                        target_reserved_quantity = 0 if location.should_bypass_reservation() else reserved_move_quantity
                        if float_compare(reserved_quantity, target_reserved_quantity, precision_rounding=product.uom_id.rounding) > 0:
                            quant_model._update_reserved_quantity(product, location, target_reserved_quantity - reserved_quantity, lot_id=lot, package_id=package, owner_id=owner)
                            released_orphan_reservation_quant_count += len(quants)
                            released_orphan_reservation_quantity += reserved_quantity - target_reserved_quantity
                    quant_groups = quant_model.sudo()._read_group(quant_domain + [("quantity", "!=", 0)], ["product_id", "location_id", "lot_id", "package_id", "owner_id"], ["quantity:sum", "id:recordset"])
                    negative_groups = [(product, location, lot, package, owner, quantity, quants) for product, location, lot, package, owner, quantity, quants in quant_groups if float_compare(quantity, 0, precision_rounding=product.uom_id.rounding) < 0]
                    if negative_groups:
                        if not (self.env.user.has_group("stock.group_stock_manager") or self.env.user.has_group("base.group_system")):
                            raise UserError(_("Inventory Manager permission is required to normalize negative stock before clearance generation."))
                        adjustment_quant_ids = []
                        for product, location, lot, package, owner, quantity, group_quants in negative_groups:
                            quant = quant_model.browse(group_quants[0].id)
                            quant.with_context(inventory_mode=True).write({"inventory_quantity": quant.quantity - quantity})
                            adjustment_quant_ids.append(quant.id)
                        quant_model.browse(adjustment_quant_ids).with_context(inventory_mode=True, set_inventory_quantity_auto_apply=True).action_apply_inventory()
                    quant_groups = quant_model.sudo()._read_group(quant_domain + [("quantity", "!=", 0)], ["product_id", "location_id", "lot_id", "package_id", "owner_id"], ["quantity:sum", "id:recordset"])
                    remaining_negative_groups = [(product, location) for product, location, lot, package, owner, quantity, group_quants in quant_groups if float_compare(quantity, 0, precision_rounding=product.uom_id.rounding) < 0]
                    if remaining_negative_groups:
                        raise UserError(_("Negative stock remains after normalization for product %(product)s at %(location)s.", product=remaining_negative_groups[0][0].display_name, location=remaining_negative_groups[0][1].display_name))
                    quant_lines = [(product, location, lot, package, owner, quantity) for product, location, lot, package, owner, quantity, group_quants in quant_groups if float_compare(quantity, 0, precision_rounding=product.uom_id.rounding) > 0]
                    if not quant_lines:
                        if negative_groups:
                            rec.write({"state": "done", "source_quant_count": 0, "normalized_negative_quant_count": len(negative_groups), "released_orphan_reservation_quant_count": released_orphan_reservation_quant_count, "released_orphan_reservation_quantity": released_orphan_reservation_quantity, "error_message": False})
                            message = _("Normalized %s negative stock dimension(s) to zero; no outbound pickings were needed.") % len(negative_groups)
                            rec.work_package_id.message_post(body=message)
                            rec.message_post(body=message)
                            continue
                        raise UserError(_("No on-hand stock matches this work package category and location scope."))
                    chunks = []
                    current_chunk = []
                    product_quants = {}
                    for line in quant_lines:
                        product_quants.setdefault(line[0].id, []).append(line)
                    for product_lines in product_quants.values():
                        if len(product_lines) <= rec.maximum_lines_per_clearance:
                            if current_chunk and len(current_chunk) + len(product_lines) > rec.maximum_lines_per_clearance:
                                chunks.append(current_chunk)
                                current_chunk = []
                            current_chunk.extend(product_lines)
                            continue
                        if current_chunk:
                            chunks.append(current_chunk)
                            current_chunk = []
                        for start_index in range(0, len(product_lines), rec.maximum_lines_per_clearance):
                            chunk = product_lines[start_index:start_index + rec.maximum_lines_per_clearance]
                            if len(chunk) == rec.maximum_lines_per_clearance:
                                chunks.append(chunk)
                            else:
                                current_chunk = chunk
                    if current_chunk:
                        chunks.append(current_chunk)
                    for quant_lines in chunks:
                        first_line = quant_lines[0]
                        picking = picking_model.create({"picking_type_id": rec.work_package_id.clearance_picking_type_id.id, "location_id": first_line[1].id, "location_dest_id": rec.work_package_id.clearance_destination_location_id.id, "origin": rec.name, "is_blind_stock_count_clearance": True, "blind_stock_count_work_package_id": rec.work_package_id.id, "blind_stock_count_clearance_batch_id": rec.id})
                        line_groups = {}
                        for line in quant_lines:
                            line_groups.setdefault((line[0].id, line[1].id), []).append(line)
                        for lines in line_groups.values():
                            first_group_line = lines[0]
                            product, location = first_group_line[:2]
                            move = move_model.create({"name": product.display_name, "product_id": product.id, "product_uom_qty": sum(line[5] for line in lines), "product_uom": product.uom_id.id, "picking_id": picking.id, "location_id": location.id, "location_dest_id": rec.work_package_id.clearance_destination_location_id.id})
                            move_line_model.create([{"move_id": move.id, "picking_id": picking.id, "product_id": product.id, "product_uom_id": product.uom_id.id, "quantity": quantity, "location_id": location.id, "location_dest_id": rec.work_package_id.clearance_destination_location_id.id, "lot_id": lot.id, "package_id": package.id, "owner_id": owner.id} for product, location, lot, package, owner, quantity in lines])
                    rec.write({"state": "done", "source_quant_count": sum(len(group_quants) for product, location, lot, package, owner, quantity, group_quants in quant_groups if float_compare(quantity, 0, precision_rounding=product.uom_id.rounding) > 0), "normalized_negative_quant_count": len(negative_groups), "released_orphan_reservation_quant_count": released_orphan_reservation_quant_count, "released_orphan_reservation_quantity": released_orphan_reservation_quantity, "error_message": False})
                    if released_orphan_reservation_quant_count:
                        message = _("Released %s stale reservation quant(s), quantity %s, before clearance generation.") % (released_orphan_reservation_quant_count, released_orphan_reservation_quantity)
                        rec.work_package_id.message_post(body=message)
                        rec.message_post(body=message)
                    if negative_groups:
                        message = _("Normalized %s negative stock dimension(s) to zero before clearance generation.") % len(negative_groups)
                        rec.work_package_id.message_post(body=message)
                        rec.message_post(body=message)
                    rec.message_post(body=_("Created %s outbound picking(s) directly from this clearance batch.") % len(chunks))
            except Exception as error:
                rec.write({"state": "failed", "error_message": str(error)})
                rec.message_post(body=_("Outbound picking generation failed: %s") % error)
        return True
