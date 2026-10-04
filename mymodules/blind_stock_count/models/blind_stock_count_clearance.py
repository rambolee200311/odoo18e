# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class BlindStockCountWorkPackage(models.Model):
    _inherit = "blind.stock.count.work.package"

    clearance_lines = fields.One2many("blind.stock.count.clearance", "work_package_id", string="Clearance Orders", copy=False)

    def action_create_clearance(self):
        clearance_model = self.env["blind.stock.count.clearance"]
        clearance_line_model = self.env["blind.stock.count.clearance.line"]
        quant_model = self.env["stock.quant"]
        clearance = False
        if not (self.env.user.has_group("blind_stock_count.group_blind_stock_count_administrator") or self.env.user.has_group("base.group_system")):
            raise UserError(_("Only a warehouse manager or system administrator can generate a clearance order."))
        for rec in self:
            if rec.state != "done":
                raise UserError(_("A clearance order can only be generated from a completed work package."))
            if clearance_model.sudo().search([("work_package_id", "=", rec.id), ("state", "!=", "cancel")], limit=1):
                raise UserError(_("An active clearance order already exists for this work package."))
            quant_domain = [("location_id.usage", "=", "internal"), ("product_id.categ_id", "child_of", rec.category_id.id), ("quantity", ">", 0)]
            if rec.location_line_ids:
                quant_domain.append(("location_id", "in", rec.location_line_ids.ids))
            quants = quant_model.sudo().search(quant_domain, order="location_id, product_id, id")
            if not quants:
                raise UserError(_("No on-hand stock matches this work package category and location scope."))
            clearance = clearance_model.create({"work_package_id": rec.id})
            clearance_line_model.create([{"clearance_id": clearance.id, "source_quant_id": quant.id, "location_id": quant.location_id.id, "product_id": quant.product_id.id, "lot_id": quant.lot_id.id, "package_id": quant.package_id.id, "owner_id": quant.owner_id.id, "quantity": quant.quantity} for quant in quants])
        return {"type": "ir.actions.act_window", "res_model": "blind.stock.count.clearance", "view_mode": "form", "res_id": clearance.id, "target": "current"} if clearance else True

    def action_cancel(self):
        clearance_model = self.env["blind.stock.count.clearance"]
        receipt_model = self.env["blind.stock.count.receipt"]
        for rec in self:
            if clearance_model.sudo().search_count([("work_package_id", "=", rec.id), ("state", "!=", "cancel")]) or receipt_model.sudo().search_count([("work_package_id", "=", rec.id), ("state", "!=", "cancel")]):
                raise UserError(_("Cancel the active clearance and receipt orders before cancelling the work package."))
        return super().action_cancel()


class BlindStockCountClearance(models.Model):
    _name = "blind.stock.count.clearance"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count Clearance"
    _order = "id desc"

    name = fields.Char(string="Clearance Number", required=True, readonly=True, copy=False, index=True, default=lambda self: self.env["ir.sequence"].next_by_code("blind.stock.count.clearance") or _("New"))
    work_package_id = fields.Many2one("blind.stock.count.work.package", string="Work Package", required=True, ondelete="restrict", copy=False, index=True, tracking=True)
    category_id = fields.Many2one(related="work_package_id.category_id", string="Product Category", readonly=True)
    location_line_ids = fields.Many2many(related="work_package_id.location_line_ids", string="Location Scope", readonly=True)
    picking_type_id = fields.Many2one("stock.picking.type", string="Outbound Operation Type", copy=False, index=True, domain=[("code", "=", "outgoing")], tracking=True)
    destination_location_id = fields.Many2one("stock.location", string="Destination Location", copy=False, index=True, domain=[("usage", "not in", ["internal", "view"])], tracking=True)
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed"), ("picking", "Picking Created"), ("done", "Done"), ("cancel", "Cancelled")], string="Status", required=True, default="draft", copy=False, index=True, tracking=True)
    clearance_lines = fields.One2many("blind.stock.count.clearance.line", "clearance_id", string="Clearance Lines", copy=False)
    picking_id = fields.Many2one("stock.picking", string="Outbound Picking", readonly=True, copy=False, index=True, tracking=True)
    return_picking_id = fields.Many2one("stock.picking", string="Return Picking", readonly=True, copy=False, index=True, tracking=True)
    note = fields.Text(string="Notes", copy=False, tracking=True)

    @api.constrains("destination_location_id")
    def check_destination_location(self):
        for rec in self:
            if rec.destination_location_id and rec.destination_location_id.usage in ("internal", "view"):
                raise ValidationError(_("The clearance destination location must be outside internal stock."))

    def action_confirm(self):
        clearance_line_model = self.env["blind.stock.count.clearance.line"]
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft clearance orders can be confirmed."))
            if not rec.picking_type_id or rec.picking_type_id.code != "outgoing":
                raise UserError(_("Select an outbound operation type before confirming."))
            if not rec.destination_location_id:
                raise UserError(_("Select a destination location before confirming."))
            if not clearance_line_model.sudo().search_count([("clearance_id", "=", rec.id)]):
                raise UserError(_("The clearance order has no stock lines."))
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "confirmed"})
        return True

    def action_create_picking(self):
        picking_model = self.env["stock.picking"]
        move_model = self.env["stock.move"]
        move_line_model = self.env["stock.move.line"]
        action = False
        for rec in self:
            if rec.state != "confirmed":
                raise UserError(_("Only confirmed clearance orders can create an outbound picking."))
            if rec.picking_id and rec.picking_id.state != "cancel":
                raise UserError(_("An active outbound picking already exists for this clearance order."))
            first_line = rec.clearance_lines[:1]
            picking = picking_model.create({"picking_type_id": rec.picking_type_id.id, "location_id": first_line.location_id.id, "location_dest_id": rec.destination_location_id.id, "origin": rec.name})
            for line in rec.clearance_lines:
                move = move_model.create({"name": line.product_id.display_name, "product_id": line.product_id.id, "product_uom_qty": line.quantity, "product_uom": line.product_id.uom_id.id, "picking_id": picking.id, "location_id": line.location_id.id, "location_dest_id": rec.destination_location_id.id})
                move_line_model.create({"move_id": move.id, "picking_id": picking.id, "product_id": line.product_id.id, "product_uom_id": line.product_id.uom_id.id, "quantity": line.quantity, "location_id": line.location_id.id, "location_dest_id": rec.destination_location_id.id, "lot_id": line.lot_id.id, "package_id": line.package_id.id, "owner_id": line.owner_id.id})
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "picking", "picking_id": picking.id})
            action = {"type": "ir.actions.act_window", "res_model": "stock.picking", "view_mode": "form", "res_id": picking.id, "target": "current"}
        return action or True

    def action_done(self):
        for rec in self:
            if rec.state != "picking" or rec.picking_id.state != "done":
                raise UserError(_("Validate the outbound picking before completing the clearance order."))
            if any(float_compare(move.quantity, move.product_uom_qty, precision_rounding=move.product_uom.rounding) != 0 for move in rec.picking_id.move_ids):
                raise UserError(_("Complete every outbound picking line before completing the clearance order."))
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "done"})
        return True

    def action_return_to_draft(self):
        receipt_model = self.env["blind.stock.count.receipt"]
        for rec in self:
            if rec.state not in ("confirmed", "picking", "done"):
                raise UserError(_("Only confirmed or processed clearance orders can be returned to draft."))
            if receipt_model.sudo().search_count([("clearance_id", "=", rec.id), ("state", "!=", "cancel")]):
                raise UserError(_("Cancel or return every linked receipt order before returning this clearance order to draft."))
            if rec.picking_id and rec.picking_id.state == "done":
                if not rec.return_picking_id or rec.return_picking_id.state != "done":
                    raise UserError(_("Create and validate a return picking before returning this clearance order to draft."))
            elif rec.picking_id and rec.picking_id.state != "cancel":
                rec.picking_id.action_cancel()
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "draft", "picking_id": False, "return_picking_id": False})
        return True

    def action_create_return_picking(self):
        return_wizard_model = self.env["stock.return.picking"]
        action = False
        for rec in self:
            if rec.state not in ("picking", "done") or rec.picking_id.state != "done":
                raise UserError(_("A validated outbound picking is required to create a return picking."))
            if rec.return_picking_id and rec.return_picking_id.state != "cancel":
                raise UserError(_("An active return picking already exists for this clearance order."))
            return_wizard = return_wizard_model.with_context(active_model="stock.picking", active_id=rec.picking_id.id, active_ids=[rec.picking_id.id]).create({"picking_id": rec.picking_id.id})
            action = return_wizard.action_create_returns_all()
            rec.with_context(blind_stock_count_processing_action=True).write({"return_picking_id": action["res_id"]})
        return action or True

    def action_cancel(self):
        for rec in self:
            if rec.state not in ("draft", "confirmed", "picking"):
                raise UserError(_("Only draft, confirmed, or unvalidated clearance orders can be cancelled."))
            if rec.picking_id and rec.picking_id.state not in ("cancel", "done"):
                rec.picking_id.action_cancel()
            if rec.picking_id and rec.picking_id.state == "done":
                raise UserError(_("Create a return picking instead of cancelling a validated clearance order."))
            rec.with_context(blind_stock_count_processing_action=True).write({"state": "cancel"})
        return True

    def action_open_picking(self):
        for rec in self:
            if not rec.picking_id:
                raise UserError(_("No outbound picking has been created."))
            return {"type": "ir.actions.act_window", "res_model": "stock.picking", "view_mode": "form", "res_id": rec.picking_id.id, "target": "current"}

    def write(self, vals):
        for rec in self:
            if rec.state in ("done", "cancel") and not self.env.context.get("blind_stock_count_processing_action"):
                raise UserError(_("Completed or cancelled clearance orders cannot be changed."))
            if "state" in vals and vals["state"] != rec.state and not self.env.context.get("blind_stock_count_processing_action"):
                raise UserError(_("The clearance order status cannot be changed directly."))
        return super().write(vals)


class BlindStockCountClearanceLine(models.Model):
    _name = "blind.stock.count.clearance.line"
    _description = "Blind Stock Count Clearance Line"
    _order = "id desc"

    clearance_id = fields.Many2one("blind.stock.count.clearance", string="Clearance Order", required=True, ondelete="cascade", copy=False, index=True)
    source_quant_id = fields.Many2one("stock.quant", string="Source Quant", readonly=True, copy=False, index=True)
    location_id = fields.Many2one("stock.location", string="Source Location", required=True, readonly=True, copy=False, index=True)
    product_id = fields.Many2one("product.product", string="Product", required=True, readonly=True, copy=False, index=True)
    lot_id = fields.Many2one("stock.lot", string="Lot / Serial Number", readonly=True, copy=False, index=True)
    package_id = fields.Many2one("stock.quant.package", string="Package", readonly=True, copy=False, index=True)
    owner_id = fields.Many2one("res.partner", string="Owner", readonly=True, copy=False, index=True)
    quantity = fields.Float(string="Quantity", required=True, readonly=True, copy=False)

    @api.constrains("quantity")
    def check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("The clearance quantity must be greater than zero."))
