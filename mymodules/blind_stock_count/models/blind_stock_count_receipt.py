# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class BlindStockCount(models.Model):
    _inherit = "blind.stock.count"

    receipt_lines = fields.One2many("blind.stock.count.receipt", "blind_stock_count_id", string="Receipt Orders", copy=False)

    def action_create_receipt(self):
        clearance_model = self.env["blind.stock.count.clearance"]
        count_model = self.env["blind.stock.count"]
        receipt_model = self.env["blind.stock.count.receipt"]
        receipt_line_model = self.env["blind.stock.count.receipt.line"]
        count_line_model = self.env["blind.stock.count.line"]
        receipt = False
        if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
            raise UserError(_("Only a warehouse manager or system administrator can generate a receipt order."))
        for rec in self:
            if rec.state != "done" or rec.is_replaced:
                raise UserError(_("Only the current completed blind stock count can generate a receipt order."))
            if rec.work_package_id.state not in ("in_progress", "done"):
                raise UserError(_("The work package must be in progress or completed before generating a receipt order."))
            if count_model.sudo().search_count([("recounted_from_id", "=", rec.id), ("state", "!=", "cancel")]):
                raise UserError(_("Cancel the active recount before generating a receipt order."))
            if receipt_model.sudo().search([("blind_stock_count_id", "=", rec.id), ("state", "!=", "cancel")], limit=1):
                raise UserError(_("An active receipt order already exists for this blind stock count."))
            clearance = clearance_model.sudo().search([("work_package_id", "=", rec.work_package_id.id), ("state", "!=", "cancel")], order="id desc", limit=1)
            if not clearance:
                raise UserError(_("Generate a clearance order for this work package before generating a receipt order."))
            receipt = receipt_model.create({"blind_stock_count_id": rec.id, "clearance_id": clearance.id})
            count_lines = count_line_model.sudo().search([("blind_stock_count_id", "=", rec.id)], order="blind_stock_count_pallet_id, product_id, id")
            receipt_line_model.create([{"receipt_id": receipt.id, "blind_stock_count_line_id": line.id, "package_id": line.blind_stock_count_pallet_id.package_id.id, "product_id": line.product_id.id, "product_tracking": line.product_tracking, "lot_name": line.lot_name, "matched_lot_id": line.matched_lot_id.id, "quantity": line.counted_qty} for line in count_lines])
        return {"type": "ir.actions.act_window", "res_model": "blind.stock.count.receipt", "view_mode": "form", "res_id": receipt.id, "target": "current"} if receipt else True

    def action_return_to_counting(self):
        receipt_model = self.env["blind.stock.count.receipt"]
        for rec in self:
            if receipt_model.sudo().search_count([("blind_stock_count_id", "=", rec.id), ("state", "!=", "cancel")]):
                raise UserError(_("Cancel the linked receipt order before returning this blind stock count to counting."))
        return super().action_return_to_counting()

    def action_create_recount(self):
        receipt_model = self.env["blind.stock.count.receipt"]
        for rec in self:
            if receipt_model.sudo().search_count([("blind_stock_count_id", "=", rec.id), ("state", "!=", "cancel")]):
                raise UserError(_("Cancel the linked receipt order before creating a recount."))
        return super().action_create_recount()


class BlindStockCountReceipt(models.Model):
    _name = "blind.stock.count.receipt"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count Receipt"
    _order = "id desc"

    name = fields.Char(string="Receipt Number", required=True, readonly=True, copy=False, index=True, default=lambda self: self.env["ir.sequence"].next_by_code("blind.stock.count.receipt") or _("New"))
    blind_stock_count_id = fields.Many2one("blind.stock.count", string="Blind Stock Count", required=True, ondelete="restrict", copy=False, index=True, tracking=True)
    work_package_id = fields.Many2one(related="blind_stock_count_id.work_package_id", string="Work Package", readonly=True, store=True, index=True)
    clearance_id = fields.Many2one("blind.stock.count.clearance", string="Clearance Order", required=True, ondelete="restrict", copy=False, index=True, tracking=True)
    location_id = fields.Many2one(related="blind_stock_count_id.location_id", string="Destination Location", readonly=True, store=True, index=True)
    source_location_id = fields.Many2one("stock.location", string="Source Location", copy=False, index=True, domain=[("usage", "not in", ["internal", "view"])], tracking=True)
    picking_type_id = fields.Many2one("stock.picking.type", string="Inbound Operation Type", copy=False, index=True, domain=[("code", "=", "incoming")], tracking=True)
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed"), ("picking", "Picking Created"), ("done", "Done"), ("cancel", "Cancelled")], string="Status", required=True, default="draft", copy=False, index=True, tracking=True)
    receipt_lines = fields.One2many("blind.stock.count.receipt.line", "receipt_id", string="Receipt Lines", copy=False)
    picking_id = fields.Many2one("stock.picking", string="Inbound Picking", readonly=True, copy=False, index=True, tracking=True)
    return_picking_id = fields.Many2one("stock.picking", string="Return Picking", readonly=True, copy=False, index=True, tracking=True)
    note = fields.Text(string="Notes", copy=False, tracking=True)

    @api.constrains("blind_stock_count_id", "clearance_id", "source_location_id")
    def check_receipt_values(self):
        for rec in self:
            if rec.blind_stock_count_id and (rec.blind_stock_count_id.state != "done" or rec.blind_stock_count_id.is_replaced):
                raise ValidationError(_("The receipt order must use a current completed blind stock count."))
            if rec.clearance_id and rec.clearance_id.work_package_id != rec.blind_stock_count_id.work_package_id:
                raise ValidationError(_("The clearance order must belong to the same work package."))
            if rec.source_location_id and rec.source_location_id.usage in ("internal", "view"):
                raise ValidationError(_("The receipt source location must be outside internal stock."))

    def action_confirm(self):
        receipt_line_model = self.env["blind.stock.count.receipt.line"]
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft receipt orders can be confirmed."))
            if not rec.picking_type_id or rec.picking_type_id.code != "incoming":
                raise UserError(_("Select an inbound operation type before confirming."))
            if not rec.source_location_id:
                raise UserError(_("Select a source location before confirming."))
            if not receipt_line_model.sudo().search_count([("receipt_id", "=", rec.id)]):
                raise UserError(_("The receipt order has no blind stock count lines."))
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "confirmed"})
        return True

    def action_create_picking(self):
        lot_model = self.env["stock.lot"]
        picking_model = self.env["stock.picking"]
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        action = False
        for rec in self:
            if rec.state != "confirmed":
                raise UserError(_("Only confirmed receipt orders can create an inbound picking."))
            if rec.clearance_id.state != "done":
                raise UserError(_("The linked clearance order must be completed before creating an inbound picking."))
            if rec.picking_id and rec.picking_id.state != "cancel":
                raise UserError(_("An active inbound picking already exists for this receipt order."))
            picking = picking_model.create({"picking_type_id": rec.picking_type_id.id, "location_id": rec.source_location_id.id, "location_dest_id": rec.location_id.id, "origin": rec.name, "partner_id": rec.work_package_id.owner_id.id})
            for line in rec.receipt_lines:
                lot = line.matched_lot_id
                if line.product_tracking != "none" and not lot:
                    lot = lot_model.sudo().search([("product_id", "=", line.product_id.id), ("name", "=", line.lot_name)], limit=1)
                    if not lot:
                        lot = lot_model.create({"name": line.lot_name, "product_id": line.product_id.id})
                if line.product_tracking != "none" and not lot:
                    raise UserError(_("A lot or serial number is required for product %s.") % line.product_id.display_name)
                if lot:
                    line.write({"lot_id": lot.id})
                move = move_model.create({"name": line.product_id.display_name, "product_id": line.product_id.id, "product_uom_qty": line.quantity, "product_uom": line.product_id.uom_id.id, "picking_id": picking.id, "location_id": rec.source_location_id.id, "location_dest_id": rec.location_id.id})
                move_line_model.create({"move_id": move.id, "picking_id": picking.id, "product_id": line.product_id.id, "product_uom_id": line.product_id.uom_id.id, "quantity": line.quantity, "location_id": rec.source_location_id.id, "location_dest_id": rec.location_id.id, "lot_id": lot.id, "result_package_id": line.package_id.id, "owner_id": rec.work_package_id.owner_id.id})
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "picking", "picking_id": picking.id})
            action = {"type": "ir.actions.act_window", "res_model": "stock.picking", "view_mode": "form", "res_id": picking.id, "target": "current"}
        return action or True

    def action_done(self):
        for rec in self:
            if rec.state != "picking" or rec.picking_id.state != "done":
                raise UserError(_("Validate the inbound picking before completing the receipt order."))
            if any(float_compare(move.quantity, move.product_uom_qty, precision_rounding=move.product_uom.rounding) != 0 for move in rec.picking_id.move_ids):
                raise UserError(_("Complete every inbound picking line before completing the receipt order."))
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "done"})
        return True

    def action_return_to_draft(self):
        for rec in self:
            if rec.state not in ("confirmed", "picking", "done"):
                raise UserError(_("Only confirmed or processed receipt orders can be returned to draft."))
            if rec.picking_id and rec.picking_id.state == "done":
                if not rec.return_picking_id or rec.return_picking_id.state != "done":
                    raise UserError(_("Create and validate a return picking before returning this receipt order to draft."))
            elif rec.picking_id and rec.picking_id.state != "cancel":
                rec.picking_id.action_cancel()
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "draft", "picking_id": False, "return_picking_id": False})
        return True

    def action_create_return_picking(self):
        return_wizard_model = self.env["stock.return.picking"]
        action = False
        for rec in self:
            if rec.state not in ("picking", "done") or rec.picking_id.state != "done":
                raise UserError(_("A validated inbound picking is required to create a return picking."))
            if rec.return_picking_id and rec.return_picking_id.state != "cancel":
                raise UserError(_("An active return picking already exists for this receipt order."))
            return_wizard = return_wizard_model.with_context(active_model="stock.picking", active_id=rec.picking_id.id, active_ids=[rec.picking_id.id]).create({"picking_id": rec.picking_id.id})
            action = return_wizard.action_create_returns_all()
            rec.with_context(blind_stock_count_processing_action=True).write({"return_picking_id": action["res_id"]})
        return action or True

    def action_cancel(self):
        for rec in self:
            if rec.state not in ("draft", "confirmed", "picking"):
                raise UserError(_("Only draft, confirmed, or unvalidated receipt orders can be cancelled."))
            if rec.picking_id and rec.picking_id.state not in ("cancel", "done"):
                rec.picking_id.action_cancel()
            if rec.picking_id and rec.picking_id.state == "done":
                raise UserError(_("Create a return picking instead of cancelling a validated receipt order."))
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "cancel"})
        return True

    def action_open_picking(self):
        for rec in self:
            if not rec.picking_id:
                raise UserError(_("No inbound picking has been created."))
            return {"type": "ir.actions.act_window", "res_model": "stock.picking", "view_mode": "form", "res_id": rec.picking_id.id, "target": "current"}

    def write(self, vals):
        for rec in self:
            if rec.state in ("done", "cancel") and not self.env.context.get("blind_stock_count_processing_action"):
                raise UserError(_("Completed or cancelled receipt orders cannot be changed."))
            if "state" in vals and vals["state"] != rec.state and not self.env.context.get("blind_stock_count_processing_action"):
                raise UserError(_("The receipt order status cannot be changed directly."))
        return super().write(vals)


class BlindStockCountReceiptLine(models.Model):
    _name = "blind.stock.count.receipt.line"
    _description = "Blind Stock Count Receipt Line"
    _order = "id desc"
    _sql_constraints = [("blind_stock_count_receipt_source_line_unique", "unique(receipt_id, blind_stock_count_line_id)", "A blind stock count line can only be received once on the same receipt order.")]

    receipt_id = fields.Many2one("blind.stock.count.receipt", string="Receipt Order", required=True, ondelete="cascade", copy=False, index=True)
    blind_stock_count_line_id = fields.Many2one("blind.stock.count.line", string="Blind Stock Count Line", required=True, readonly=True, ondelete="restrict", copy=False, index=True)
    package_id = fields.Many2one("stock.quant.package", string="Pallet Number", readonly=True, copy=False, index=True)
    product_id = fields.Many2one("product.product", string="Product", required=True, readonly=True, copy=False, index=True)
    product_tracking = fields.Selection([("none", "No Tracking"), ("lot", "By Lots"), ("serial", "By Unique Serial Number")], string="Tracking", required=True, readonly=True, copy=False, index=True)
    lot_name = fields.Char(string="Lot / Serial Number", readonly=True, copy=False, index=True)
    matched_lot_id = fields.Many2one("stock.lot", string="Matched Lot / Serial Number", readonly=True, copy=False, index=True)
    lot_id = fields.Many2one("stock.lot", string="Receipt Lot / Serial Number", readonly=True, copy=False, index=True)
    quantity = fields.Float(string="Counted Quantity", required=True, readonly=True, copy=False)

    @api.constrains("quantity", "product_tracking", "lot_name")
    def check_line_values(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("The receipt quantity must be greater than zero."))
            if rec.product_tracking != "none" and not rec.lot_name:
                raise ValidationError(_("A lot or serial number is required for a tracked product."))
            if rec.product_tracking == "serial" and rec.quantity != 1:
                raise ValidationError(_("A serial-numbered product must have a quantity of 1 per line."))
