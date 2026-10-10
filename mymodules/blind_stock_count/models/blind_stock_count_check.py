# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BlindStockCountCheck(models.Model):
    _name = "blind.stock.count.check"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count Check"
    _order = "id desc"

    name = fields.Char(string="Check Number", required=True, readonly=True, copy=False, index=True, default=lambda self: self.env["ir.sequence"].next_by_code("blind.stock.count.check") or _("New"))
    blind_stock_count_id = fields.Many2one("blind.stock.count", string="Blind Stock Count", required=True, ondelete="restrict", copy=False, index=True, tracking=True)
    work_package_id = fields.Many2one(related="blind_stock_count_id.work_package_id", string="Work Package", readonly=True, store=True, index=True)
    location_id = fields.Many2one(related="blind_stock_count_id.location_id", string="Count Location", readonly=True, store=True, index=True)
    state = fields.Selection([("draft", "Draft"), ("checking", "Checking"), ("done", "Done"), ("cancel", "Cancelled")], string="Status", required=True, default="draft", copy=False, index=True, tracking=True)
    check_lines = fields.One2many("blind.stock.count.check.line", "blind_stock_count_check_id", string="Check Lines", copy=False)
    checked_by_id = fields.Many2one("res.users", string="Checked By", required=True, default=lambda self: self.env.user.id, readonly=True, copy=False, index=True)
    checked_at = fields.Datetime(string="Checked At", readonly=True, copy=False, index=True)
    conclusion = fields.Selection([("pending", "Pending"), ("passed", "Passed"), ("failed", "Failed"), ("uncertain", "Uncertain")], string="Conclusion", required=True, default="pending", copy=False, index=True, tracking=True)
    conclusion_note = fields.Text(string="Conclusion Notes", copy=False, tracking=True)
    note = fields.Text(string="Notes", copy=False)

    @api.constrains("blind_stock_count_id")
    def check_blind_stock_count(self):
        for rec in self:
            if rec.blind_stock_count_id.state != "done":
                raise UserError(_("Only completed blind stock counts can be checked."))

    @api.model_create_multi
    def create(self, vals_list):
        count_model = self.env["blind.stock.count"]
        for vals in vals_list:
            count = count_model.sudo().search([("id", "=", vals.get("blind_stock_count_id")), ("state", "=", "done")], limit=1)
            if not count:
                raise UserError(_("Select a completed blind stock count."))
        return super().create(vals_list)

    def action_start_checking(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft blind stock count checks can be started."))
            if rec.blind_stock_count_id.state != "done":
                raise UserError(_("The source blind stock count must be completed."))
            rec.with_context(blind_stock_count_check_action=True).write({"state": "checking", "checked_by_id": self.env.user.id, "checked_at": fields.Datetime.now()})
        return True

    def action_done(self, conclusion=False, conclusion_note=False):
        check_line_model = self.env["blind.stock.count.check.line"]
        for rec in self:
            if rec.state != "checking":
                raise UserError(_("Only active blind stock count checks can be completed."))
            if not check_line_model.sudo().search_count([("blind_stock_count_check_id", "=", rec.id)]):
                raise UserError(_("Record at least one sampled line before completing the blind stock count check."))
            result = conclusion or rec.conclusion
            if result not in ("passed", "failed", "uncertain"):
                raise UserError(_("Pending cannot be completed. Select Passed, Failed, or Uncertain."))
            values = {"state": "done", "checked_at": fields.Datetime.now(), "conclusion": result}
            if conclusion_note is not False:
                values["conclusion_note"] = conclusion_note
            rec.with_context(blind_stock_count_check_action=True).write(values)
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state not in ("draft", "checking"):
                raise UserError(_("Only draft or active blind stock count checks can be cancelled."))
            rec.with_context(blind_stock_count_check_action=True).write({"state": "cancel"})
        return True

    def action_open_scan(self):
        for rec in self:
            if rec.state != "checking":
                raise UserError(_("Only active blind stock count checks can be scanned."))
            return {"type": "ir.actions.client", "tag": "blind_stock_count.check_scan", "target": "main", "params": {"blind_stock_count_check_id": rec.id}}

    def get_active_check(self, check_id):
        check = self.sudo().search([("id", "=", check_id), ("state", "=", "checking")], limit=1)
        if not check:
            raise UserError(_("The active blind stock count check was not found."))
        return check

    @api.model
    def get_pda_check_list(self):
        checks = self.sudo().search([("state", "in", ["draft", "checking", "done"])], order="id desc")
        return [{"id": rec.id, "name": rec.name, "state": rec.state, "conclusion": rec.conclusion, "count_name": rec.blind_stock_count_id.name, "work_package_name": rec.work_package_id.display_name, "location_name": rec.location_id.display_name} for rec in checks]

    def get_check_line_data(self, check_lines):
        result = []
        for line in check_lines:
            product = line.product_id or line.scanned_product_id
            result.append({"id": line.id, "product_id": product.id, "name": product.display_name or line.scanned_product_barcode or _("Unknown Product"), "barcode": product.barcode or line.scanned_product_barcode or "", "tracking": line.product_tracking or product.tracking or "", "lot_name": line.lot_name or line.scanned_lot_name or "", "checked_qty": line.checked_qty, "is_matched": line.is_matched, "match_status": line.match_status})
        return result

    def get_pallet_scan_data(self, source_pallet):
        check_line_model = self.env["blind.stock.count.check.line"]
        result = []
        pallet_codes = [code for code in [source_pallet.package_id.barcode, source_pallet.package_id.name] if code]
        for rec in self:
            domain = [("blind_stock_count_check_id", "=", rec.id), "|", ("source_pallet_id", "=", source_pallet.id), ("scanned_pallet_code", "in", pallet_codes)]
            check_lines = check_line_model.sudo().search(domain, order="id desc")
            product_summaries = {}
            for line in check_lines:
                product = line.product_id or line.scanned_product_id
                key = product.id or line.scanned_product_barcode or line.id
                summary = product_summaries.setdefault(key, {"id": product.id, "name": product.display_name or line.scanned_product_barcode or _("Unknown Product"), "checked_qty": 0.0})
                summary["checked_qty"] += line.checked_qty
            result.append({"id": source_pallet.id, "source_pallet_id": source_pallet.id, "name": source_pallet.package_id.name, "barcode": source_pallet.package_id.barcode or source_pallet.package_id.name, "line_count": len(check_lines), "product_summaries": list(product_summaries.values()), "product_lines": rec.get_check_line_data(check_lines)})
        return result[0] if len(result) == 1 else result

    def get_anomaly_pallet_scan_data(self, pallet_code):
        check_line_model = self.env["blind.stock.count.check.line"]
        result = []
        for rec in self:
            check_lines = check_line_model.sudo().search([("blind_stock_count_check_id", "=", rec.id), ("source_line_id", "=", False), ("scanned_pallet_code", "=", pallet_code)], order="id desc")
            product_summaries = {}
            for line in check_lines:
                product = line.scanned_product_id
                key = product.id or line.scanned_product_barcode or line.id
                summary = product_summaries.setdefault(key, {"id": product.id, "name": product.display_name or line.scanned_product_barcode or _("Unknown Product"), "checked_qty": 0.0})
                summary["checked_qty"] += line.checked_qty
            result.append({"id": "anomaly:%s" % pallet_code, "source_pallet_id": False, "name": pallet_code, "barcode": pallet_code, "line_count": len(check_lines), "product_summaries": list(product_summaries.values()), "product_lines": rec.get_check_line_data(check_lines)})
        return result[0] if len(result) == 1 else result

    @api.model
    def get_check_scan_data(self, check_id):
        check = self.sudo().search([("id", "=", check_id), ("state", "in", ["checking", "done"])], limit=1)
        if not check:
            raise UserError(_("The blind stock count check was not found."))
        pallet_model = self.env["blind.stock.count.pallet"]
        check_line_model = self.env["blind.stock.count.check.line"]
        check_lines = check_line_model.sudo().search([("blind_stock_count_check_id", "=", check.id)])
        source_pallet_ids = check_lines.source_pallet_id.ids
        source_pallets = pallet_model.sudo().search([("id", "in", source_pallet_ids)], order="id desc")
        source_pallet_codes = set(source_pallets.mapped("package_id.barcode") + source_pallets.mapped("package_id.name"))
        anomaly_pallet_codes = {line.scanned_pallet_code for line in check_lines.filtered(lambda line: not line.source_line_id and line.scanned_pallet_code) if line.scanned_pallet_code not in source_pallet_codes}
        pallets = [check.get_pallet_scan_data(source_pallet) for source_pallet in source_pallets] + [check.get_anomaly_pallet_scan_data(pallet_code) for pallet_code in sorted(anomaly_pallet_codes)]
        return {"check": {"id": check.id, "name": check.name, "state": check.state, "count_name": check.blind_stock_count_id.name, "location_name": check.location_id.display_name, "conclusion": check.conclusion, "conclusion_note": check.conclusion_note or ""}, "pallets": pallets}

    @api.model
    def action_scan_location(self, check_id, barcode):
        check = self.get_active_check(check_id)
        barcode = (barcode or "").strip()
        if not barcode:
            raise UserError(_("Please scan the count location."))
        locations = self.env["stock.location"].sudo().search([("usage", "=", "internal"), "|", "|", ("barcode", "=", barcode), ("complete_name", "=", barcode), ("name", "=", barcode)], limit=2)
        if not locations:
            raise UserError(_("No internal location matches this barcode."))
        if len(locations) > 1:
            raise UserError(_("More than one internal location matches this barcode."))
        if locations != check.location_id:
            raise UserError(_("The scanned location does not match the blind stock count location."))
        return {"message": _("Location verified. Now scan a pallet.")}

    @api.model
    def action_scan_package(self, check_id, barcode):
        check = self.get_active_check(check_id)
        barcode = (barcode or "").strip()
        if not barcode:
            raise UserError(_("Please scan a pallet."))
        pallet_model = self.env["blind.stock.count.pallet"]
        source_pallets = pallet_model.sudo().search([("blind_stock_count_id", "=", check.blind_stock_count_id.id), "|", ("package_id.barcode", "=", barcode), ("package_id.name", "=", barcode)], limit=2)
        if len(source_pallets) > 1:
            raise UserError(_("More than one pallet matches this barcode."))
        if source_pallets:
            return {"pallet": check.get_pallet_scan_data(source_pallets), "message": _("Pallet checked. Now scan a product.")}
        check_line_model = self.env["blind.stock.count.check.line"]
        pallet_anomaly = check_line_model.sudo().search([("blind_stock_count_check_id", "=", check.id), ("source_line_id", "=", False), ("scanned_pallet_code", "=", barcode), ("scanned_product_barcode", "=", False)], limit=1)
        if not pallet_anomaly:
            check_line_model.create({"blind_stock_count_check_id": check.id, "anomaly_status": "not_in_blind", "scanned_pallet_code": barcode, "checked_qty": 0.0})
        return {"pallet": check.get_anomaly_pallet_scan_data(barcode), "message": _("Pallet is not recorded on this blind stock count. The anomaly was recorded; now scan a product."), "message_type": "warning"}

    @api.model
    def get_scanned_pallet(self, check_id, barcode):
        check = self.get_active_check(check_id)
        barcode = (barcode or "").strip()
        if not barcode:
            return False
        source_pallets = self.env["blind.stock.count.pallet"].sudo().search([("blind_stock_count_id", "=", check.blind_stock_count_id.id), "|", ("package_id.barcode", "=", barcode), ("package_id.name", "=", barcode)], limit=2)
        if len(source_pallets) > 1:
            raise UserError(_("More than one pallet matches this barcode."))
        return {"pallet": check.get_pallet_scan_data(source_pallets), "message": _("Pallet checked. Now scan a product.")} if source_pallets else False

    @api.model
    def action_scan_product(self, check_id, source_pallet_id, pallet_code, barcode):
        check = self.get_active_check(check_id)
        barcode = (barcode or "").strip()
        if not barcode:
            raise UserError(_("Please scan a product barcode."))
        source_pallet = self.env["blind.stock.count.pallet"].sudo().search([("id", "=", source_pallet_id), ("blind_stock_count_id", "=", check.blind_stock_count_id.id)], limit=1) if source_pallet_id else False
        pallet_code = (pallet_code or source_pallet.package_id.barcode or source_pallet.package_id.name or "").strip()
        source_line_model = self.env["blind.stock.count.line"]
        check_line_model = self.env["blind.stock.count.check.line"]
        source_lines = source_line_model.sudo().search([("blind_stock_count_pallet_id", "=", source_pallet.id), ("blind_stock_count_id", "=", check.blind_stock_count_id.id), ("product_id.barcode", "=", barcode)]) if source_pallet else self.env["blind.stock.count.line"]
        products = source_lines.mapped("product_id")
        if source_lines and len(products) == 1:
            product = products[0]
            manual_source_line = source_lines.filtered(lambda line: not line.lot_name)[:1]
            manual_check_line = check_line_model.sudo().search([("blind_stock_count_check_id", "=", check.id), ("source_line_id", "=", manual_source_line.id)], limit=1) if product.tracking == "none" else False
            checked_serial_count = check_line_model.sudo().search_count([("blind_stock_count_check_id", "=", check.id), ("source_pallet_id", "=", source_pallet.id), ("product_id", "=", product.id), ("product_tracking", "=", "serial")])
            return {"product": {"id": product.id, "name": product.display_name, "barcode": product.barcode or "", "tracking": product.tracking, "checked_qty": manual_check_line.checked_qty if manual_check_line else "", "checked_serial_count": checked_serial_count, "anomaly_status": False}, "message": _("Product checked.")}
        product_model = self.env["product.product"]
        products = product_model.sudo().search([("barcode", "=", barcode)], limit=2)
        if len(products) != 1:
            check_line_model.create({"blind_stock_count_check_id": check.id, "anomaly_status": "not_in_blind", "scanned_pallet_code": pallet_code, "scanned_product_barcode": barcode, "checked_qty": 0.0})
            return {"pallet": check.get_pallet_scan_data(source_pallet) if source_pallet else check.get_anomaly_pallet_scan_data(pallet_code), "recorded_anomaly": True, "message": _("Product is not recorded on this blind stock count. The anomaly was recorded."), "message_type": "warning"}
        product = products[0]
        if not product_model.sudo().search([("id", "=", product.id), ("categ_id", "child_of", check.work_package_id.category_id.id)], limit=1):
            return {"product": {"id": product.id, "name": product.display_name, "barcode": product.barcode or "", "tracking": product.tracking, "checked_qty": "", "checked_serial_count": 0, "anomaly_status": "out_of_scope"}, "message": _("Product is outside the work package product category. Continue scanning to record the anomaly."), "message_type": "warning"}
        return {"product": {"id": product.id, "name": product.display_name, "barcode": product.barcode or "", "tracking": product.tracking, "checked_qty": "", "checked_serial_count": 0, "anomaly_status": "not_in_blind"}, "message": _("Product is not recorded on this blind stock count. Continue scanning to record the anomaly."), "message_type": "warning"}

    @api.model
    def action_scan_serial_numbers(self, check_id, source_pallet_id, pallet_code, product_id, barcode, anomaly_status=False):
        check = self.get_active_check(check_id)
        serial_numbers = [serial_number.strip() for serial_number in (barcode or "").replace("，", ",").split(",")]
        if not serial_numbers or any(not serial_number for serial_number in serial_numbers):
            raise UserError(_("Enter one or more serial numbers separated by commas."))
        if len(serial_numbers) != len(set(serial_numbers)):
            raise UserError(_("The same serial number cannot be entered twice."))
        source_line_model = self.env["blind.stock.count.line"]
        check_line_model = self.env["blind.stock.count.check.line"]
        product = self.env["product.product"].sudo().search([("id", "=", product_id), ("tracking", "=", "serial")], limit=1)
        if not product:
            raise UserError(_("The serial-numbered product was not found."))
        source_pallet = self.env["blind.stock.count.pallet"].sudo().search([("id", "=", source_pallet_id), ("blind_stock_count_id", "=", check.blind_stock_count_id.id)], limit=1) if source_pallet_id else False
        pallet_code = (pallet_code or source_pallet.package_id.barcode or source_pallet.package_id.name or "").strip()
        source_lines = source_line_model.sudo().search([("blind_stock_count_pallet_id", "=", source_pallet.id), ("blind_stock_count_id", "=", check.blind_stock_count_id.id), ("product_id", "=", product.id), ("product_tracking", "=", "serial"), ("lot_name", "in", serial_numbers)]) if source_pallet else self.env["blind.stock.count.line"]
        source_line_by_name = {line.lot_name: line for line in source_lines}
        existing_check_line = check_line_model.sudo().search([("blind_stock_count_check_id", "=", check.id), ("source_line_id", "in", source_lines.ids)], limit=1) if source_lines else False
        if existing_check_line:
            raise UserError(_("Serial number %s has already been sampled on this blind stock count check.") % existing_check_line.lot_name)
        check_lines = check_line_model.create([{"blind_stock_count_check_id": check.id, "source_line_id": source_line_by_name[serial_number].id, "checked_qty": 1.0} if serial_number in source_line_by_name and not anomaly_status else {"blind_stock_count_check_id": check.id, "anomaly_status": anomaly_status or "not_matched", "scanned_pallet_code": pallet_code, "scanned_product_id": product.id, "scanned_product_barcode": product.barcode or "", "scanned_lot_name": serial_number, "checked_qty": 1.0} for serial_number in serial_numbers])
        checked_serial_count = check_line_model.sudo().search_count([("blind_stock_count_check_id", "=", check.id), ("source_pallet_id", "=", source_pallet.id), ("product_id", "=", product.id), ("product_tracking", "=", "serial")]) if source_pallet else 0
        pallet_data = check.get_pallet_scan_data(source_pallet) if source_pallet else check.get_anomaly_pallet_scan_data(pallet_code)
        return {"line_ids": check_lines.ids, "pallet": pallet_data, "checked_serial_count": checked_serial_count, "message": _("%s serial number(s) checked.") % len(check_lines), "message_type": "warning" if any(not line.is_matched for line in check_lines) else "success"}

    @api.model
    def action_add_quantity(self, check_id, source_pallet_id, pallet_code, product_id, lot_name, quantity, anomaly_status=False):
        check = self.get_active_check(check_id)
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise UserError(_("Enter a valid checked quantity."))
        if quantity <= 0:
            raise UserError(_("The checked quantity must be greater than zero."))
        source_line_model = self.env["blind.stock.count.line"]
        check_line_model = self.env["blind.stock.count.check.line"]
        product = self.env["product.product"].sudo().search([("id", "=", product_id)], limit=1)
        if not product:
            raise UserError(_("The product was not found."))
        source_pallet = self.env["blind.stock.count.pallet"].sudo().search([("id", "=", source_pallet_id), ("blind_stock_count_id", "=", check.blind_stock_count_id.id)], limit=1) if source_pallet_id else False
        pallet_code = (pallet_code or source_pallet.package_id.barcode or source_pallet.package_id.name or "").strip()
        source_line_domain = [("blind_stock_count_pallet_id", "=", source_pallet.id), ("blind_stock_count_id", "=", check.blind_stock_count_id.id), ("product_id", "=", product.id)]
        if lot_name:
            source_line_domain += [("product_tracking", "=", "lot"), ("lot_name", "=", lot_name)]
        else:
            source_line_domain += [("product_tracking", "=", "none"), ("lot_name", "=", False)]
        source_line = source_line_model.sudo().search(source_line_domain, limit=1) if source_pallet else False
        if source_line and not anomaly_status:
            check_line = check_line_model.sudo().search([("blind_stock_count_check_id", "=", check.id), ("source_line_id", "=", source_line.id)], limit=1)
            if check_line:
                check_line = check_line_model.browse(check_line.id)
                check_line.write({"checked_qty": quantity})
            else:
                check_line = check_line_model.create({"blind_stock_count_check_id": check.id, "source_line_id": source_line.id, "checked_qty": quantity})
        else:
            check_line = check_line_model.create({"blind_stock_count_check_id": check.id, "anomaly_status": anomaly_status or "not_matched", "scanned_pallet_code": pallet_code, "scanned_product_id": product.id, "scanned_product_barcode": product.barcode or "", "scanned_lot_name": lot_name or False, "checked_qty": quantity})
        pallet_data = check.get_pallet_scan_data(source_pallet) if source_pallet else check.get_anomaly_pallet_scan_data(pallet_code)
        return {"line_ids": check_line.ids, "pallet": pallet_data, "message": _("Sample quantity recorded."), "is_matched": check_line.is_matched, "match_status": check_line.match_status}

    def write(self, vals):
        for rec in self:
            if rec.state in ("done", "cancel"):
                raise UserError(_("Completed or cancelled blind stock count checks cannot be changed."))
            if "state" in vals and vals["state"] != rec.state and not self.env.context.get("blind_stock_count_check_action"):
                raise UserError(_("The blind stock count check status cannot be changed directly."))
            if rec.state != "draft" and "blind_stock_count_id" in vals:
                raise UserError(_("The source blind stock count cannot be changed after checking starts."))
        return super().write(vals)
