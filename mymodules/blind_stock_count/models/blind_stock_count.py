# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class BlindStockCount(models.Model):
    _name = "blind.stock.count"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count"
    _order = "id desc"

    name = fields.Char(string="Blind Stock Count", required=True, readonly=True, copy=False, default=lambda self: self.env["ir.sequence"].next_by_code("blind.stock.count") or _("New"))
    date = fields.Datetime(string="Count Date", required=True, default=fields.Datetime.now, copy=False, tracking=True)
    work_package_id = fields.Many2one("blind.stock.count.work.package", string="Work Package", copy=False, index=True, tracking=True)
    product_category_id = fields.Many2one(related="work_package_id.category_id", string="Product Category", readonly=True)
    location_id = fields.Many2one("stock.location", string="Count Location", required=True, copy=False, index=True, domain=[("usage", "=", "internal")], tracking=True)
    state = fields.Selection([("draft", "Draft"), ("counting", "Counting"), ("done", "Done"), ("cancel", "Cancelled")], string="Status", required=True, default="draft", copy=False, index=True, tracking=True)
    pallet_lines = fields.One2many("blind.stock.count.pallet", "blind_stock_count_id", string="Pallets", copy=False)
    note = fields.Text(string="Notes", copy=False, tracking=True)

    @api.constrains("work_package_id", "location_id")
    def check_work_package_and_location(self):
        for rec in self:
            if not rec.work_package_id:
                continue
            if rec.location_id.usage != "internal":
                raise ValidationError(_("The count location must be an internal location."))
            if rec.work_package_id.location_line_ids and rec.location_id not in rec.work_package_id.location_line_ids:
                raise ValidationError(_("The count location is outside the selected work package location scope."))

    @api.model_create_multi
    def create(self, vals_list):
        work_package_model = self.env["blind.stock.count.work.package"]
        for vals in vals_list:
            work_package = work_package_model.sudo().search([("id", "=", vals.get("work_package_id"))], limit=1)
            if not work_package:
                raise UserError(_("A work package is required to create a blind stock count."))
            if work_package.state != "in_progress":
                raise UserError(_("Blind stock counts can only be created in an in-progress work package."))
        return super().create(vals_list)

    def check_product_for_count(self, product):
        product_model = self.env["product.product"]
        for rec in self:
            if not rec.work_package_id or not rec.product_category_id:
                raise UserError(_("Select a work package with a product category."))
            for product_rec in product:
                if not product_model.sudo().search([("id", "=", product_rec.id), ("categ_id", "child_of", rec.product_category_id.id)], limit=1):
                    raise UserError(_("The product does not belong to the selected work package category."))
        return True

    def action_start_counting(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft blind stock counts can be started."))
            if not rec.work_package_id or not rec.product_category_id:
                raise UserError(_("Select a work package with a product category."))
            if rec.location_id.usage != "internal":
                raise UserError(_("The count location must be an internal location."))
            if rec.work_package_id.location_line_ids and rec.location_id not in rec.work_package_id.location_line_ids:
                raise UserError(_("The count location is outside the selected work package location scope."))
            rec.write({"state": "counting"})
        return True

    def action_done(self):
        for rec in self:
            if rec.state != "counting":
                raise UserError(_("Only active blind stock counts can be completed."))
            rec.write({"state": "done"})
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state not in ("draft","counting"):
                raise UserError(_("Only draft can be cancelled."))
            rec.write({"state": "cancel"})
        return True

    def action_open_continue_scan(self):
        for rec in self:
            if rec.state != "counting":
                raise UserError(_("Only active blind stock counts can continue scanning."))
            return {"type": "ir.actions.client", "tag": "blind_stock_count.scan", "target": "main", "params": {"blind_stock_count_id": rec.id}}

    def write(self, vals):
        protected_fields = {"work_package_id", "location_id"}
        pallet_model = self.env["blind.stock.count.pallet"]
        line_model = self.env["blind.stock.count.line"]
        for rec in self:
            if rec.state in ("done", "cancel"):
                raise UserError(_("Completed or cancelled blind stock counts cannot be changed."))
            protected_values = protected_fields.intersection(vals)
            if rec.state == "counting" and protected_values and not (protected_values == {"work_package_id"} and not rec.work_package_id and vals.get("work_package_id")):
                raise UserError(_("Work package and location cannot be changed after counting starts."))
            if vals.get("state") == "done" and not pallet_model.sudo().search_count([("blind_stock_count_id", "=", rec.id)]):
                raise UserError(_("Record at least one pallet before completing the blind stock count."))
            if vals.get("state") == "done" and not line_model.sudo().search_count([("blind_stock_count_id", "=", rec.id)]):
                raise UserError(_("Record at least one product line before completing the blind stock count."))
        return super().write(vals)

    # def unlink(self):
    #     for rec in self:
    #         if rec.state != "draft":
    #             raise UserError(_("Only draft blind stock counts can be deleted."))
    #     return super().unlink()

    @api.model
    def get_scannable_work_packages(self):
        work_packages = self.env["blind.stock.count.work.package"].sudo().search([("state", "=", "in_progress")], order="id desc")
        return [{"id": rec.id, "name": rec.display_name, "category_name": rec.category_id.display_name, "owner_name": rec.owner_id.display_name, "location_names": ", ".join(rec.location_line_ids.mapped("display_name"))} for rec in work_packages]

    @api.model
    def get_continue_scan_data(self, count_id):
        count = self.sudo().search([("id", "=", count_id), ("state", "in", ["draft", "counting"])], limit=1)
        if not count:
            raise UserError(_("The unfinished blind stock count was not found."))
        if not count.work_package_id:
            raise UserError(_("Select a work package on the blind stock count before continuing PDA scanning."))
        if count.work_package_id.state != "in_progress":
            raise UserError(_("The work package is not active."))
        if count.state == "draft":
            self.browse(count.id).action_start_counting()
            count = self.sudo().browse(count.id)
        pallets = self.env["blind.stock.count.pallet"].sudo().search([("blind_stock_count_id", "=", count.id)], order="id desc")
        pallet_data = pallets.get_scan_data()
        return {"work_package": {"id": count.work_package_id.id, "name": count.work_package_id.display_name}, "count": {"id": count.id, "name": count.name, "location_name": count.location_id.display_name}, "pallets": pallet_data if isinstance(pallet_data, list) else [pallet_data] if pallet_data else []}

    @api.model
    def get_pda_count_list(self, work_package_id):
        work_package = self.env["blind.stock.count.work.package"].sudo().search([("id", "=", work_package_id)], limit=1)
        if not work_package:
            raise UserError(_("The blind stock count work package was not found."))
        if work_package.state != "in_progress":
            raise UserError(_("The work package is not active."))
        counts = self.sudo().search([("work_package_id", "=", work_package.id)], order="id desc")
        return [{"id": rec.id, "name": rec.name, "date": rec.date, "work_package_name": rec.work_package_id.display_name, "location_name": rec.location_id.display_name, "state": rec.state} for rec in counts]

    @api.model
    def action_scan_location(self, work_package_id, barcode):
        work_package = self.env["blind.stock.count.work.package"].sudo().search([("id", "=", work_package_id)], limit=1)
        if not work_package or not work_package.category_id:
            raise UserError(_("Please select a work package with a product category."))
        if work_package.state != "in_progress":
            raise UserError(_("The work package is not active."))
        barcode = (barcode or "").strip()
        if not barcode:
            raise UserError(_("Please scan an internal location."))
        locations = self.env["stock.location"].sudo().search([("usage", "=", "internal"), "|", "|", ("barcode", "=", barcode), ("complete_name", "=", barcode), ("name", "=", barcode)], limit=2)
        if not locations:
            raise UserError(_("No internal location matches this barcode."))
        if len(locations) > 1:
            raise UserError(_("More than one internal location matches this barcode."))
        if work_package.location_line_ids and locations not in work_package.location_line_ids:
            raise UserError(_("The scanned location is outside the selected work package location scope."))
        count = self.create({"work_package_id": work_package.id, "location_id": locations.id, "state": "counting"})
        return {"count": {"id": count.id, "name": count.name, "location_name": count.location_id.display_name}, "message": _("Location scanned. Now scan a pallet.")}

    @api.model
    def action_scan_package(self, count_id, barcode):
        count = self.sudo().search([("id", "=", count_id), ("state", "=", "counting")], limit=1)
        if not count:
            raise UserError(_("The active blind stock count was not found."))
        barcode = (barcode or "").strip()
        if not barcode:
            raise UserError(_("Please scan a pallet."))
        packages = self.env["stock.quant.package"].sudo().search(["|", ("barcode", "=", barcode), ("name", "=", barcode)], limit=2)
        if not packages:
            raise UserError(_("No pallet matches this barcode."))
        if len(packages) > 1:
            raise UserError(_("More than one pallet matches this barcode."))
        pallet = self.env["blind.stock.count.pallet"].sudo().search([("blind_stock_count_id", "=", count.id), ("package_id", "=", packages.id)], limit=1)
        if not pallet:
            pallet = self.env["blind.stock.count.pallet"].create({"blind_stock_count_id": count.id, "package_id": packages.id})
        return {"pallet": pallet.get_scan_data(), "message": _("Pallet scanned. Now scan a product.")}

    @api.model
    def action_scan_product(self, pallet_id, barcode):
        pallet = self.env["blind.stock.count.pallet"].sudo().search([("id", "=", pallet_id), ("state", "=", "counting")], limit=1)
        if not pallet:
            raise UserError(_("The active blind stock count pallet was not found."))
        barcode = (barcode or "").strip()
        if not barcode:
            raise UserError(_("Please scan a product barcode."))
        products = self.env["product.product"].sudo().search([("barcode", "=", barcode), ("categ_id", "child_of", pallet.blind_stock_count_id.product_category_id.id)], limit=2)
        if not products:
            raise UserError(_("No work package product matches this barcode."))
        if len(products) > 1:
            raise UserError(_("More than one work package product matches this barcode."))
        pallet.blind_stock_count_id.check_product_for_count(products)
        manual_line = self.env["blind.stock.count.line"].sudo().search([("blind_stock_count_pallet_id", "=", pallet.id), ("product_id", "=", products.id), ("lot_name", "=", False)], order="id desc", limit=1)
        scanned_serial_count = self.env["blind.stock.count.line"].sudo().search_count([("blind_stock_count_pallet_id", "=", pallet.id), ("product_id", "=", products.id), ("lot_name", "!=", False)])
        return {"product": {"id": products.id, "name": products.display_name, "barcode": products.barcode or "", "tracking": products.tracking, "manual_line_id": manual_line.id if manual_line else False, "counted_qty": manual_line.counted_qty if manual_line else "", "scanned_serial_count": scanned_serial_count}, "message": _("Product scanned.")}

    @api.model
    def action_scan_serial_numbers(self, pallet_id, product_id, barcode):
        pallet = self.env["blind.stock.count.pallet"].sudo().search([("id", "=", pallet_id), ("state", "=", "counting")], limit=1)
        product = self.env["product.product"].sudo().search([("id", "=", product_id)], limit=1)
        if not pallet or not product:
            raise UserError(_("The active pallet or product was not found."))
        if product.tracking != "serial":
            raise UserError(_("This product does not use serial numbers."))
        pallet.blind_stock_count_id.check_product_for_count(product)
        serial_numbers = [serial_number.strip() for serial_number in (barcode or "").replace("，", ",").split(",")]
        if not serial_numbers or any(not serial_number for serial_number in serial_numbers):
            raise UserError(_("Enter one or more serial numbers separated by commas."))
        if len(serial_numbers) != len(set(serial_numbers)):
            raise UserError(_("The same serial number cannot be entered twice."))
        duplicate_line = self.env["blind.stock.count.line"].sudo().search([("work_package_id", "=", pallet.blind_stock_count_id.work_package_id.id), ("product_id", "=", product.id), ("lot_name", "in", serial_numbers), ("state", "!=", "cancel")], limit=1)
        if duplicate_line:
            raise UserError(_("Serial number %s is already recorded in blind stock count %s, pallet %s, product %s.") % (duplicate_line.lot_name, duplicate_line.blind_stock_count_id.name, duplicate_line.blind_stock_count_pallet_id.package_id.name, duplicate_line.product_id.display_name))
        product_lines = self.env["blind.stock.count.line"].create([{"blind_stock_count_pallet_id": pallet.id, "product_id": product.id, "lot_name": serial_number, "counted_qty": 1.0} for serial_number in serial_numbers])
        scanned_serial_count = self.env["blind.stock.count.line"].sudo().search_count([("blind_stock_count_pallet_id", "=", pallet.id), ("product_id", "=", product.id), ("lot_name", "!=", False)])
        return {"created_count": len(serial_numbers), "line_ids": product_lines.ids, "pallet": pallet.get_scan_data(), "scanned_serial_count": scanned_serial_count, "message": _("%s serial number(s) recorded.") % len(serial_numbers)}

    @api.model
    def action_add_lot_quantity(self, pallet_id, product_id, lot_name, quantity):
        pallet = self.env["blind.stock.count.pallet"].sudo().search([("id", "=", pallet_id), ("state", "=", "counting")], limit=1)
        product = self.env["product.product"].sudo().search([("id", "=", product_id)], limit=1)
        if not pallet or not product:
            raise UserError(_("The active pallet or product was not found."))
        if product.tracking != "lot":
            raise UserError(_("This product does not use batch tracking."))
        pallet.blind_stock_count_id.check_product_for_count(product)
        lot_name = (lot_name or "").strip()
        if not lot_name:
            raise UserError(_("Enter a batch number."))
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise UserError(_("Enter a valid counted quantity."))
        if quantity <= 0:
            raise UserError(_("The counted quantity must be greater than zero."))
        line_model = self.env["blind.stock.count.line"]
        product_line = line_model.sudo().search([("blind_stock_count_pallet_id", "=", pallet.id), ("product_id", "=", product.id), ("lot_name", "=", lot_name), ("state", "!=", "cancel")], limit=1)
        if product_line:
            product_line = line_model.browse(product_line.id)
            product_line.write({"counted_qty": product_line.counted_qty + quantity})
        else:
            product_line = line_model.create({"blind_stock_count_pallet_id": pallet.id, "product_id": product.id, "lot_name": lot_name, "counted_qty": quantity})
        return {"line_ids": product_line.ids, "pallet": pallet.get_scan_data(), "message": _("Batch quantity recorded.")}

    @api.model
    def action_add_manual_quantity(self, pallet_id, product_id, quantity):
        pallet = self.env["blind.stock.count.pallet"].sudo().search([("id", "=", pallet_id), ("state", "=", "counting")], limit=1)
        product = self.env["product.product"].sudo().search([("id", "=", product_id)], limit=1)
        if not pallet or not product:
            raise UserError(_("The active pallet or product was not found."))
        if product.tracking != "none":
            raise UserError(_("This product requires serial number scanning."))
        pallet.blind_stock_count_id.check_product_for_count(product)
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise UserError(_("Enter a valid counted quantity."))
        if quantity <= 0:
            raise UserError(_("The counted quantity must be greater than zero."))
        line_model = self.env["blind.stock.count.line"]
        product_line = line_model.sudo().search([("blind_stock_count_pallet_id", "=", pallet.id), ("product_id", "=", product.id), ("lot_name", "=", False)], order="id desc", limit=1)
        if product_line:
            product_line = line_model.browse(product_line.id)
            product_line.write({"counted_qty": quantity})
        else:
            product_line = line_model.create({"blind_stock_count_pallet_id": pallet.id, "product_id": product.id, "counted_qty": quantity})
        return {"line_ids": product_line.ids, "pallet": pallet.get_scan_data(), "message": _("Quantity recorded.")}

    @api.model
    def action_delete_line(self, line_id):
        line_model = self.env["blind.stock.count.line"]
        line = line_model.sudo().search([("id", "=", line_id), ("state", "=", "counting")], limit=1)
        if not line:
            raise UserError(_("The active blind stock count line was not found."))
        pallet_id = line.blind_stock_count_pallet_id.id
        product_id = line.product_id.id
        line_model.browse(line.id).unlink()
        pallet = self.env["blind.stock.count.pallet"].sudo().search([("id", "=", pallet_id), ("state", "=", "counting")], limit=1)
        scanned_serial_count = line_model.sudo().search_count([("blind_stock_count_pallet_id", "=", pallet.id), ("product_id", "=", product_id), ("lot_name", "!=", False)])
        return {"pallet": pallet.get_scan_data(), "product_id": product_id, "scanned_serial_count": scanned_serial_count, "message": _("Recorded line deleted.")}
