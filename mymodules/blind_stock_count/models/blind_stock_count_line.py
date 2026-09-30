# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class BlindStockCountLine(models.Model):
    _name = "blind.stock.count.line"
    _description = "Blind Stock Count Line"
    _order = "id desc"

    blind_stock_count_pallet_id = fields.Many2one("blind.stock.count.pallet", string="Blind Stock Count Pallet", required=True, ondelete="cascade", copy=False, index=True)
    blind_stock_count_id = fields.Many2one(related="blind_stock_count_pallet_id.blind_stock_count_id", string="Blind Stock Count", readonly=True, store=True, index=True)
    work_package_id = fields.Many2one(related="blind_stock_count_id.work_package_id", string="Work Package", readonly=True, store=True, index=True)
    product_category_id = fields.Many2one(related="blind_stock_count_id.product_category_id", string="Product Category", readonly=True)
    state = fields.Selection(related="blind_stock_count_id.state", string="Status", readonly=True, store=True, index=True)
    product_id = fields.Many2one("product.product", string="Product", required=True, copy=False, index=True)
    product_barcode = fields.Char(related="product_id.barcode", string="Product Barcode", readonly=True)
    product_tracking = fields.Selection(related="product_id.tracking", string="Tracking", readonly=True, store=True, index=True)
    lot_name = fields.Char(string="Lot / Serial Number", copy=False, index=True)
    matched_lot_id = fields.Many2one("stock.lot", string="Matched Serial Number", compute="_compute_matched_lot_id", store=True, readonly=True, copy=False, index=True, compute_sudo=True)
    counted_qty = fields.Float(string="Counted Quantity", required=True, default=1.0, copy=False)
    counted_by_id = fields.Many2one("res.users", string="Counted By", required=True, default=lambda self: self.env.user.id, readonly=True, copy=False, index=True)
    counted_at = fields.Datetime(string="Counted At", required=True, default=fields.Datetime.now, readonly=True, copy=False, index=True)
    note = fields.Char(string="Notes", copy=False)

    def init(self):
        self.env.cr.execute("ALTER TABLE blind_stock_count_line DROP CONSTRAINT IF EXISTS blind_stock_count_project_product_serial_unique")
        self.env.cr.execute("DROP INDEX IF EXISTS blind_stock_count_line_serial_active_unique")
        self.env.cr.execute("DROP INDEX IF EXISTS blind_stock_count_line_work_package_product_serial_active_unique")
        self.env.cr.execute("DROP INDEX IF EXISTS blind_stock_count_line_lot_pallet_product_active_unique")
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS blind_stock_count_line_work_package_product_serial_active_unique
            ON blind_stock_count_line (work_package_id, product_id, lot_name)
            WHERE work_package_id IS NOT NULL AND lot_name IS NOT NULL AND product_tracking = 'serial' AND (state IS NULL OR state != 'cancel')
        """)
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS blind_stock_count_line_lot_pallet_product_active_unique
            ON blind_stock_count_line (blind_stock_count_pallet_id, product_id, lot_name)
            WHERE lot_name IS NOT NULL AND product_tracking = 'lot' AND (state IS NULL OR state != 'cancel')
        """)
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS blind_stock_count_line_manual_product_active_unique
            ON blind_stock_count_line (blind_stock_count_pallet_id, product_id)
            WHERE lot_name IS NULL AND (state IS NULL OR state != 'cancel')
        """)

    @api.depends("product_id", "product_id.tracking", "lot_name", "blind_stock_count_pallet_id.blind_stock_count_id.location_id")
    def _compute_matched_lot_id(self):
        quant_model = self.env["stock.quant"]
        for rec in self:
            rec.matched_lot_id = False
            if rec.product_id.tracking == "none" or not rec.lot_name or not rec.blind_stock_count_id.location_id:
                continue
            quant = quant_model.sudo().search([("product_id", "=", rec.product_id.id), ("lot_id.name", "=", rec.lot_name), ("location_id", "=", rec.blind_stock_count_id.location_id.id), ("location_id.usage", "=", "internal"), ("quantity", ">", 0)], limit=1)
            rec.matched_lot_id = quant.lot_id

    @api.model_create_multi
    def create(self, vals_list):
        pallet_model = self.env["blind.stock.count.pallet"]
        product_model = self.env["product.product"]
        manual_product_keys = set()
        for vals in vals_list:
            lot_name = (vals.get("lot_name") or "").strip()
            vals["lot_name"] = lot_name or False
            pallet = pallet_model.sudo().search([("id", "=", vals.get("blind_stock_count_pallet_id")), ("state", "=", "counting")], limit=1)
            product = product_model.sudo().search([("id", "=", vals.get("product_id"))], limit=1)
            if not pallet or not product:
                raise UserError(_("An active blind stock count pallet and product are required."))
            pallet.blind_stock_count_id.check_product_for_count(product)
            if product.tracking != "none" and not vals["lot_name"]:
                raise UserError(_("A serial number is required for this product."))
            if product.tracking == "none":
                vals["lot_name"] = False
                manual_product_key = (pallet.id, product.id)
                duplicate_line = self.sudo().search([("blind_stock_count_pallet_id", "=", pallet.id), ("product_id", "=", product.id), ("lot_name", "=", False), ("state", "!=", "cancel")], limit=1)
                if manual_product_key in manual_product_keys or duplicate_line:
                    raise UserError(_("This non-tracked product is already recorded on this pallet. Update its quantity instead."))
                manual_product_keys.add(manual_product_key)
        return super().create(vals_list)

    @api.constrains("product_id", "lot_name", "counted_qty")
    def check_line_values(self):
        for rec in self:
            rec.blind_stock_count_id.check_product_for_count(rec.product_id)
            if rec.counted_qty <= 0:
                raise ValidationError(_("The counted quantity must be greater than zero."))
            if rec.product_id.tracking != "none" and not rec.lot_name:
                raise ValidationError(_("A serial number is required for this product."))
            if rec.product_id.tracking == "serial" and rec.counted_qty != 1:
                raise ValidationError(_("A serial-numbered product must have a counted quantity of 1 per line."))
            if rec.product_id.tracking == "none" and rec.lot_name:
                raise ValidationError(_("A non-tracked product cannot have a serial number."))

    def write(self, vals):
        if {"blind_stock_count_pallet_id", "product_id"}.intersection(vals):
            raise UserError(_("Delete and add the line again to change its pallet or product."))
        if "matched_lot_id" in vals:
            raise UserError(_("The matched serial number is managed automatically."))
        if "lot_name" in vals and len(self) > 1:
            raise UserError(_("Update serial numbers one line at a time."))
        for rec in self:
            if rec.state != "counting":
                raise UserError(_("Blind stock count lines can only be changed while counting is active."))
            if "lot_name" in vals:
                lot_name = (vals["lot_name"] or "").strip()
                vals["lot_name"] = lot_name or False
                if rec.product_id.tracking == "none":
                    vals["lot_name"] = False
                elif not vals["lot_name"]:
                    raise UserError(_("A serial number is required for this product."))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state != "counting":
                raise UserError(_("Blind stock count lines can only be deleted while counting is active."))
        return super().unlink()
