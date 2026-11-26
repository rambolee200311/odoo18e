# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class BlindStockCountWorkPackage(models.Model):
    _inherit = "blind.stock.count.work.package"

    delayed_outbound_batch_lines = fields.One2many("blind.stock.count.delayed.outbound.batch", "work_package_id", string="Delayed Outbound Batches", copy=False)
    delayed_outbound_picking_lines = fields.One2many("stock.picking", "blind_stock_count_work_package_id", string="Delayed Outbound Pickings", domain=[("is_blind_stock_count_delayed_outbound", "=", True)], copy=False)

    def action_open_generate_delayed_outbound_wizard(self):
        wizard_model = self.env["blind.stock.count.generate.delayed.outbound.batch"]
        for rec in self:
            if rec.state != "done":
                raise UserError(_("Delayed outbound pickings can only be generated from a completed work package."))
            if not rec.clearance_picking_type_id or rec.clearance_picking_type_id.code != "outgoing":
                raise UserError(_("Select an outgoing operation type on the work package before generating delayed outbound pickings."))
            if not rec.clearance_destination_location_id:
                raise UserError(_("Select an outbound destination location on the work package before generating delayed outbound pickings."))
            wizard = wizard_model.create({"work_package_id": rec.id})
            return {"type": "ir.actions.act_window", "name": _("Queue Generate Outbound Pickings"), "res_model": "blind.stock.count.generate.delayed.outbound.batch", "view_mode": "form", "res_id": wizard.id, "target": "new"}
        return True

    def action_open_delayed_outbound_picking_list(self):
        delayed_outbound_picking_list_view = self.env.ref("blind_stock_count.view_blind_stock_count_delayed_outbound_picking_list")
        for rec in self:
            return {"type": "ir.actions.act_window", "name": _("Generated Outbound Pickings"), "res_model": "stock.picking", "view_mode": "list,form", "views": [(delayed_outbound_picking_list_view.id, "list"), (False, "form")], "domain": [("blind_stock_count_work_package_id", "=", rec.id), ("is_blind_stock_count_delayed_outbound", "=", True)], "context": {"create": False, "edit": False, "delete": False, "blind_stock_count_delayed_outbound_list": True}, "target": "current"}
        return True


class BlindStockCountDelayedOutboundBatch(models.Model):
    _name = "blind.stock.count.delayed.outbound.batch"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count Delayed Outbound Batch"
    _order = "id desc"

    name = fields.Char(string="Delayed Outbound Batch Number", required=True, readonly=True, copy=False, index=True, default=lambda self: self.env["ir.sequence"].next_by_code("blind.stock.count.delayed.outbound.batch") or _("New"))
    work_package_id = fields.Many2one("blind.stock.count.work.package", string="Work Package", required=True, ondelete="restrict", copy=False, index=True, tracking=True)
    category_id = fields.Many2one(related="work_package_id.category_id", string="Product Category", readonly=True)
    date_from = fields.Date(string="Date From", required=True, readonly=True, copy=False, index=True)
    date_to = fields.Date(string="Date To", required=True, readonly=True, copy=False, index=True)
    outbound_picking_lines = fields.One2many("stock.picking", "blind_stock_count_delayed_outbound_batch_id", string="Outbound Pickings", copy=False)
    result_line_ids = fields.One2many("blind.stock.count.delayed.outbound.batch.line", "batch_id", string="Generation Results", copy=False)
    candidate_picking_count = fields.Integer(string="Candidate Picking Count", required=True, readonly=True, copy=False, default=0)
    generated_picking_count = fields.Integer(string="Generated Picking Count", required=True, readonly=True, copy=False, default=0)
    skipped_picking_count = fields.Integer(string="Skipped Picking Count", required=True, readonly=True, copy=False, default=0)
    requested_by_id = fields.Many2one("res.users", string="Requested By", required=True, readonly=True, default=lambda self: self.env.user, copy=False, index=True)
    requested_at = fields.Datetime(string="Requested At", required=True, readonly=True, default=fields.Datetime.now, copy=False, index=True)
    state = fields.Selection([("queued", "Queued"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")], string="Status", required=True, readonly=True, default="queued", copy=False, index=True, tracking=True)
    queue_job_id = fields.Many2one("queue.job", string="Queue Job", readonly=True, ondelete="set null", copy=False, index=True)
    error_message = fields.Text(string="Error Message", readonly=True, copy=False)

    def action_open_delayed_outbound_result_list(self):
        result_list_view = self.env.ref("blind_stock_count.view_blind_stock_count_delayed_outbound_batch_line_list")
        for rec in self:
            return {"type": "ir.actions.act_window", "name": _("Generation Results"), "res_model": "blind.stock.count.delayed.outbound.batch.line", "view_mode": "list", "views": [(result_list_view.id, "list")], "domain": [("batch_id", "=", rec.id)], "context": {"create": False, "edit": False, "delete": True}, "target": "current"}
        return True

    def job_generate_delayed_outbound_pickings(self):
        move_line_model = self.env["stock.move.line"]
        move_model = self.env["stock.move"]
        picking_model = self.env["stock.picking"]
        product_model = self.env["product.product"]
        quant_model = self.env["stock.quant"]
        batch_line_model = self.env["blind.stock.count.delayed.outbound.batch.line"]
        for rec in self:
            rec.write({"state": "running", "error_message": False})
            try:
                with self.env.cr.savepoint():
                    work_package = rec.work_package_id
                    if work_package.state != "done":
                        raise UserError(_("Delayed outbound pickings can only be generated from a completed work package."))
                    if not work_package.clearance_picking_type_id or work_package.clearance_picking_type_id.code != "outgoing":
                        raise UserError(_("Select an outgoing operation type on the work package before generating delayed outbound pickings."))
                    if not work_package.clearance_destination_location_id:
                        raise UserError(_("Select an outbound destination location on the work package before generating delayed outbound pickings."))
                    product_ids = product_model.sudo().search([("categ_id", "child_of", work_package.category_id.id)]).ids
                    if not product_ids:
                        rec.write({"state": "done", "candidate_picking_count": 0, "generated_picking_count": 0, "skipped_picking_count": 0, "error_message": False})
                        rec.message_post(body=_("No products match the work package category."))
                        continue
                    source_pickings = picking_model.sudo().search([("outbound_order_id", "!=", False), ("outbound_order_id.state", "!=", "cancel"), ("outbound_order_id.date", ">=", rec.date_from), ("outbound_order_id.date", "<=", rec.date_to), ("picking_type_id.code", "=", "internal"), ("state", "=", "done"), ("move_ids.product_id", "in", product_ids)], order="id")
                    generated_picking_count = 0
                    skipped_picking_count = 0
                    available_by_quant_id = {}
                    for source_picking in source_pickings:
                        existing_generated_picking = picking_model.sudo().search([("blind_stock_count_source_picking_id", "=", source_picking.id), ("blind_stock_count_work_package_id", "=", work_package.id), ("state", "!=", "cancel")], limit=1)
                        if existing_generated_picking:
                            batch_line_model.create({"batch_id": rec.id, "source_picking_id": source_picking.id, "outbound_picking_id": existing_generated_picking.id, "state": "skipped", "skip_reason": _("A delayed outbound picking already exists for this source: %s") % existing_generated_picking.name})
                            skipped_picking_count += 1
                            continue
                        existing_outbound_picking = picking_model.sudo().search([("origin", "=", source_picking.name), ("picking_type_id.code", "=", "outgoing"), ("state", "!=", "cancel")], limit=1)
                        if existing_outbound_picking:
                            batch_line_model.create({"batch_id": rec.id, "source_picking_id": source_picking.id, "outbound_picking_id": existing_outbound_picking.id, "state": "skipped", "skip_reason": _("An active outbound picking already exists: %s") % existing_outbound_picking.name})
                            skipped_picking_count += 1
                            continue
                        allocations_by_move_id = {}
                        source_moves = source_picking.move_ids.filtered(lambda move: move.state == "done" and move.product_id.id in product_ids)
                        for source_move in source_moves:
                            allocations = []
                            source_lines = source_move.move_line_ids.filtered(lambda line: line.state == "done" and not float_is_zero(line.quantity_product_uom, precision_rounding=line.product_id.uom_id.rounding))
                            for source_line in source_lines:
                                quant_domain = [("product_id", "=", source_line.product_id.id), ("quantity", ">", 0), ("location_id.usage", "=", "internal")]
                                if source_line.product_id.tracking == "serial" and source_line.lot_id:
                                    quant_domain.append(("lot_id", "=", source_line.lot_id.id))
                                if work_package.location_line_ids:
                                    quant_domain.append(("location_id", "in", work_package.location_line_ids.ids))
                                quants = quant_model.sudo().search(quant_domain, order="in_date asc, id asc")
                                remaining_quantity = source_line.quantity_product_uom
                                for quant in quants:
                                    available_quantity = available_by_quant_id.get(quant.id, max(quant.quantity - quant.reserved_quantity, 0.0))
                                    if float_compare(available_quantity, 0.0, precision_rounding=source_line.product_id.uom_id.rounding) <= 0:
                                        continue
                                    allocated_quantity = min(available_quantity, remaining_quantity)
                                    allocations.append((allocated_quantity, quant.location_id, quant.lot_id, quant.package_id, quant.owner_id))
                                    available_by_quant_id[quant.id] = available_quantity - allocated_quantity
                                    remaining_quantity -= allocated_quantity
                                    if float_compare(remaining_quantity, 0.0, precision_rounding=source_line.product_id.uom_id.rounding) <= 0:
                                        break
                            if allocations:
                                allocations_by_move_id[source_move.id] = (source_move, allocations)
                        if not allocations_by_move_id:
                            batch_line_model.create({"batch_id": rec.id, "source_picking_id": source_picking.id, "state": "skipped", "skip_reason": _("No available internal stock matched the products and serial numbers in this work package category.")})
                            skipped_picking_count += 1
                            continue
                        first_allocations = next(iter(allocations_by_move_id.values()))[1]
                        first_location = first_allocations[0][1]
                        outbound_picking = picking_model.create({"picking_type_id": work_package.clearance_picking_type_id.id, "location_id": first_location.id, "location_dest_id": work_package.clearance_destination_location_id.id, "origin": source_picking.name, "partner_id": source_picking.outbound_order_id.unload_company.id, "outbound_order_id": source_picking.outbound_order_id.id, "is_blind_stock_count_delayed_outbound": True, "blind_stock_count_work_package_id": work_package.id, "blind_stock_count_delayed_outbound_batch_id": rec.id, "blind_stock_count_source_picking_id": source_picking.id})
                        for source_move, allocations in allocations_by_move_id.values():
                            quantity = sum(allocation[0] for allocation in allocations)
                            if float_is_zero(quantity, precision_rounding=source_move.product_id.uom_id.rounding):
                                continue
                            move_values = {"name": source_move.name, "product_id": source_move.product_id.id, "product_uom_qty": quantity, "product_uom": source_move.product_id.uom_id.id, "picking_id": outbound_picking.id, "location_id": allocations[0][1].id, "location_dest_id": work_package.clearance_destination_location_id.id, "move_orig_ids": [(4, source_move.id)]}
                            if source_move.outbound_order_product_id:
                                move_values["outbound_order_product_id"] = source_move.outbound_order_product_id
                            outbound_move = move_model.create(move_values)
                            move_line_model.create([{"move_id": outbound_move.id, "picking_id": outbound_picking.id, "product_id": source_move.product_id.id, "product_uom_id": source_move.product_id.uom_id.id, "quantity": allocation[0], "location_id": allocation[1].id, "location_dest_id": work_package.clearance_destination_location_id.id, "lot_id": allocation[2].id, "package_id": allocation[3].id, "owner_id": allocation[4].id} for allocation in allocations])
                        batch_line_model.create({"batch_id": rec.id, "source_picking_id": source_picking.id, "outbound_picking_id": outbound_picking.id, "state": "generated"})
                        generated_picking_count += 1
                    rec.write({"state": "done", "candidate_picking_count": len(source_pickings), "generated_picking_count": generated_picking_count, "skipped_picking_count": skipped_picking_count, "error_message": False})
                    message = _("Generated %(generated)s delayed outbound picking(s) from %(candidate)s candidate picking(s); skipped %(skipped)s picking(s).", generated=generated_picking_count, candidate=len(source_pickings), skipped=skipped_picking_count)
                    rec.message_post(body=message)
                    work_package.message_post(body=message)
            except Exception as error:
                rec.write({"state": "failed", "error_message": str(error)})
                rec.message_post(body=_("Delayed outbound picking generation failed: %s") % error)
        return True


class BlindStockCountDelayedOutboundBatchLine(models.Model):
    _name = "blind.stock.count.delayed.outbound.batch.line"
    _description = "Blind Stock Count Delayed Outbound Batch Line"
    _order = "id desc"
    _sql_constraints = [("blind_stock_count_delayed_outbound_batch_line_unique", "unique(batch_id, source_picking_id)", "A source picking can only appear once in the same delayed outbound batch.")]

    batch_id = fields.Many2one("blind.stock.count.delayed.outbound.batch", string="Delayed Outbound Batch", required=True, ondelete="cascade", copy=False, index=True)
    source_picking_id = fields.Many2one("stock.picking", string="Source Picking", required=True, ondelete="restrict", copy=False, index=True)
    source_picking_state = fields.Selection(related="source_picking_id.state", string="Picking Status", readonly=True, store=True)
    outbound_picking_id = fields.Many2one("stock.picking", string="Related Outbound Picking", readonly=True, ondelete="set null", copy=False, index=True)
    outbound_picking_state = fields.Selection(related="outbound_picking_id.state", string="Outbound Pick Status", readonly=True, store=True)
    state = fields.Selection([("generated", "Generated"), ("skipped", "Skipped"), ("deleted", "Deleted")], string="Result", required=True, readonly=True, copy=False, index=True)
    skip_reason = fields.Text(string="Skip Reason", readonly=True, copy=False)
