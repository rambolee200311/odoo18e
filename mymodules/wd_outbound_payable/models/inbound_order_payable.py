# -*- coding: utf-8 -*-

import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"

    warehouse_operation_charge_lines = fields.One2many("world.depot.inbound.order.charge", "inbound_order_id", string="Warehouse Operation Charges", domain=[("is_warehouse_operation_charge", "=", True)], copy=False)
    receivable_state = fields.Selection([("draft", "Charge Unconfirmed"), ("confirmed", "Charge Confirmed")], string="Receivable Status", default="draft", required=True, tracking=True, index=True, copy=False)
    receivable_confirm_user_id = fields.Many2one("res.users", string="Receivable Confirmed By", readonly=True, index=True, copy=False)
    receivable_confirm_time = fields.Datetime(string="Receivable Confirmed On", readonly=True, index=True, copy=False)
    currency_id = fields.Many2one("res.currency", string="Currency", default=lambda self: self.env.company.currency_id.id, copy=False, index=True)
    charge_calculation_remark = fields.Text(string="Charge Calculation Remark", copy=False)
    statement_inbound_date = fields.Date(string="Statement Inbound Date", compute="_compute_statement_inbound_date", store=True, readonly=True, index=True)
    statement_period_id = fields.Many2one("statement.period", string="Statement Period", ondelete="set null", readonly=True, index=True, copy=False)
    statement_period_id_state = fields.Selection(related="statement_period_id.state", string="Statement Period State", store=True, readonly=True, index=True)

    @api.depends("project.stock_report_date_mode", "actual_inbound_date", "stock_picking_id.date_done", "confirm_time_server")
    def _compute_statement_inbound_date(self):
        for rec in self:
            if getattr(rec.project, "stock_report_date_mode", "validation") == "business":
                rec.statement_inbound_date = rec.actual_inbound_date or (fields.Datetime.to_datetime(rec.confirm_time_server).date() if rec.confirm_time_server else False)
            else:
                inbound_datetime = rec.stock_picking_id.date_done or rec.confirm_time_server
                rec.statement_inbound_date = fields.Datetime.to_datetime(inbound_datetime).date() if inbound_datetime else False

    def prepare_inbound_charge_values(self):
        charge_data_by_order_id = {}
        for rec in self:
            quotation = getattr(rec.project, "quotation_id", False)
            charge_values = []
            remarks = []
            if not quotation:
                charge_data_by_order_id[rec.id] = {"charge_values": charge_values, "currency_id": False, "remark": False}
                continue
            quotation_lines = quotation.quotation_wh_in_lines.filtered(lambda line: line.active)
            has_pallet_weight_tier = any(line.charge_item_id.charge_billing_object == "pallet" and line.charge_item_id.is_weight_tier for line in quotation_lines)
            has_carton_weight_tier = any(line.charge_item_id.charge_billing_object == "carton" and line.charge_item_id.is_weight_tier for line in quotation_lines)
            pallet_charge_data = []
            if any(line.charge_item_id.charge_billing_object == "pallet" for line in quotation_lines):
                if getattr(rec.project, "pallet_structure_mode", "known") == "unknown":
                    for actual_pallet in getattr(rec, "actual_pallet_lines", False).filtered(lambda pallet: pallet.state != "void"):
                        gross_weight = 0.0
                        is_weight_complete = bool(actual_pallet.product_lines)
                        for product_line in actual_pallet.product_lines:
                            product_gross_weight = product_line.product_id.gross_weight or 0.0
                            product_net_weight = product_line.product_id.weight or 0.0
                            product_weight = product_gross_weight if math.isfinite(product_gross_weight) and product_gross_weight > 0 else product_net_weight
                            if product_weight <= 0:
                                is_weight_complete = False
                            gross_weight += (product_line.quantity or 0.0) * product_weight
                        pallet_charge_data.append((1.0, gross_weight if is_weight_complete and gross_weight > 0 else False))
                else:
                    for pallet_line in rec.inbound_order_product_ids:
                        pallet_quantity = pallet_line.pallets or 0.0
                        gross_weight = 0.0
                        is_weight_complete = bool(pallet_line.inbound_order_product_pallet_ids)
                        for product_line in pallet_line.inbound_order_product_pallet_ids:
                            product_gross_weight = False
                            try:
                                product_gross_weight = float(getattr(product_line, "gross_weight", False))
                            except (TypeError, ValueError):
                                product_gross_weight = False
                            product_net_weight = product_line.product_id.weight or 0.0
                            product_weight = product_gross_weight if product_gross_weight and math.isfinite(product_gross_weight) and product_gross_weight > 0 else product_net_weight
                            if not product_weight or not math.isfinite(product_weight) or product_weight <= 0:
                                is_weight_complete = False
                            else:
                                gross_weight += (product_line.quantity or 0.0) * product_weight
                        if pallet_quantity > 0:
                            pallet_charge_data.append((pallet_quantity, gross_weight if is_weight_complete and gross_weight > 0 else False))
            carton_charge_data = []
            if any(line.charge_item_id.charge_billing_object == "carton" for line in quotation_lines):
                for pallet_line in rec.inbound_order_product_ids:
                    for product_line in pallet_line.inbound_order_product_pallet_ids:
                        carton_quantity = (product_line.quantity or 0.0) * (pallet_line.pallets or 0.0)
                        try:
                            product_gross_weight = float(getattr(product_line, "gross_weight", False))
                        except (TypeError, ValueError):
                            product_gross_weight = False
                        product_net_weight = product_line.product_id.weight or 0.0
                        product_weight = product_gross_weight if product_gross_weight and math.isfinite(product_gross_weight) and product_gross_weight > 0 else product_net_weight
                        if not product_weight or not math.isfinite(product_weight) or product_weight <= 0:
                            product_weight = False
                        if carton_quantity > 0:
                            carton_charge_data.append((carton_quantity, product_weight))
            missing_pallet_quantity = sum(quantity for quantity, gross_weight in pallet_charge_data if not gross_weight)
            missing_carton_quantity = sum(quantity for quantity, gross_weight in carton_charge_data if not gross_weight)
            if has_pallet_weight_tier and missing_pallet_quantity:
                remarks.append(_("Gross and net weight are both missing for %s pallets, so their weight-tier charges were not generated.") % missing_pallet_quantity)
            if has_carton_weight_tier and missing_carton_quantity:
                remarks.append(_("Gross and net weight are both missing for %s cartons, so their weight-tier charges were not generated.") % missing_carton_quantity)
            for quotation_line in quotation_lines:
                charge_item = quotation_line.charge_item_id
                quantity = 0.0
                if quotation_line.is_fixed_fee or not charge_item.charge_billing_object:
                    quantity = 1.0
                elif charge_item.charge_billing_object == "pallet":
                    if charge_item.is_weight_tier:
                        quantity = sum(
                            pallet_quantity for pallet_quantity, gross_weight in pallet_charge_data
                            if gross_weight and gross_weight > charge_item.minimum_gross_weight
                            and (not charge_item.maximum_gross_weight or gross_weight <= charge_item.maximum_gross_weight)
                        )
                    else:
                        quantity = sum(pallet_quantity for pallet_quantity, gross_weight in pallet_charge_data)
                elif charge_item.charge_billing_object == "carton":
                    if charge_item.is_weight_tier:
                        quantity = sum(
                            carton_quantity for carton_quantity, gross_weight in carton_charge_data
                            if gross_weight and gross_weight > charge_item.minimum_gross_weight
                            and (not charge_item.maximum_gross_weight or gross_weight <= charge_item.maximum_gross_weight)
                        )
                    else:
                        quantity = sum(carton_quantity for carton_quantity, gross_weight in carton_charge_data)
                if quantity:
                    charge_values.append((0, 0, {
                        "charge_item_id": charge_item.id,
                        "charge_billing_object": "fixed" if quotation_line.is_fixed_fee else charge_item.charge_billing_object,
                        "quantity": quantity,
                        "charge_unit_id": charge_item.unit_id.id,
                        "unit_price": quotation_line.unit_price,
                        "currency_id": quotation.currency_id.id,
                        "description": quotation_line.remark or _("Generated from quotation %s") % quotation.display_name,
                        "quotation_id": quotation.id,
                        "quotation_line_id": quotation_line.id,
                        "is_import_quotation_charge": True,
                    }))
            charge_data_by_order_id[rec.id] = {"charge_values": charge_values, "currency_id": quotation.currency_id.id, "remark": "\n".join(remarks) or False}
        return charge_data_by_order_id

    def action_confirm(self):
        charge_data_by_order_id = self.prepare_inbound_charge_values()
        result = super().action_confirm()
        self.apply_inbound_charge_values(charge_data_by_order_id)
        return result

    def apply_inbound_charge_values(self, charge_data_by_order_id):
        env_charge = self.env["world.depot.inbound.order.charge"]
        for rec in self:
            charge_data = charge_data_by_order_id[rec.id]
            values = {"currency_id": charge_data["currency_id"]} if charge_data["currency_id"] else {}
            existing_charge_lines = rec.inbound_order_charge_ids.filtered(lambda line: line.is_import_quotation_charge)
            existing_charge_by_quotation_line_id = {line.quotation_line_id.id: line for line in existing_charge_lines}
            quotation_line_ids = set()
            for _, _, charge_values in charge_data["charge_values"]:
                quotation_line_ids.add(charge_values["quotation_line_id"])
                existing_charge_line = existing_charge_by_quotation_line_id.get(charge_values["quotation_line_id"])
                if existing_charge_line:
                    existing_charge_line.write(charge_values)
                else:
                    env_charge.create({**charge_values, "inbound_order_id": rec.id})
            existing_charge_lines.filtered(lambda line: line.quotation_line_id.id not in quotation_line_ids).unlink()
            values["charge_calculation_remark"] = charge_data["remark"]
            if values:
                rec.write(values)

    def action_add_quotation_charges(self):
        for rec in self:
            if rec.state != "confirm":
                raise ValidationError(_("Only confirmed inbound orders can add quotation charges."))
            if rec.receivable_state == "confirmed":
                raise ValidationError(_("Confirmed receivable charges cannot be changed."))
            if rec.statement_period_id and rec.statement_period_id.state != "draft":
                raise ValidationError(_("Charge lines cannot be changed after the statement period is confirmed."))
        self.apply_inbound_charge_values(self.prepare_inbound_charge_values())
        return True

    def action_add_warehouse_operation_charges(self):
        env_vas_order = self.env["wd.vas.order"]
        for rec in self:
            if rec.state != "confirm":
                raise ValidationError(_("Only confirmed inbound orders can add warehouse operation charges."))
            if rec.receivable_state == "confirmed":
                raise ValidationError(_("Confirmed receivable charges cannot be changed."))
            if rec.statement_period_id and rec.statement_period_id.state != "draft":
                raise ValidationError(_("Charge lines cannot be changed after the statement period is confirmed."))
            vas_order_ids = env_vas_order.sudo().search([("inbound_order_id", "=", rec.id), ("state", "=", "submitted")]).ids
            env_vas_order.browse(vas_order_ids).sync_inbound_warehouse_operation_charges()
        return True

    def action_confirm_receivable(self):
        for rec in self:
            if rec.state == "cancel":
                raise ValidationError(_("Cancelled inbound orders cannot confirm receivable."))
            if rec.receivable_state == "confirmed":
                raise ValidationError(_("Receivable is already confirmed."))
            if not rec.inbound_order_charge_ids:
                raise ValidationError(_("Charge lines are required before confirming receivable."))
            seen_charge_item_ids = set()
            duplicate_charge_item_names = set()
            for charge_line in rec.inbound_order_charge_ids:
                if charge_line.charge_item_id.id in seen_charge_item_ids:
                    duplicate_charge_item_names.add(charge_line.charge_item_id.display_name)
                else:
                    seen_charge_item_ids.add(charge_line.charge_item_id.id)
            if duplicate_charge_item_names:
                raise ValidationError(_("Duplicate charge items are not allowed across inbound and warehouse operation fees: %s") % ", ".join(sorted(duplicate_charge_item_names)))
            if rec.inbound_order_charge_ids.filtered(lambda line: (line.amount or 0.0) <= 0):
                raise ValidationError(_("Each charge line amount must be greater than zero before confirming receivable."))
            rec.write({"receivable_state": "confirmed", "receivable_confirm_user_id": self.env.user.id, "receivable_confirm_time": fields.Datetime.now()})
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Receivable"), "message": _("Receivable confirmed successfully."), "type": "success",
            "sticky": False, "next": {"type": "ir.actions.client", "tag": "soft_reload"},
        }}

    def action_unconfirm_receivable(self):
        for rec in self:
            if rec.state == "cancel":
                raise ValidationError(_("Cancelled inbound orders cannot unconfirm receivable."))
            if rec.receivable_state != "confirmed":
                raise ValidationError(_("Receivable is not confirmed."))
            if rec.statement_period_id and rec.statement_period_id.state != "draft":
                raise ValidationError(_("Receivable cannot be unconfirmed after the statement period is confirmed."))
            rec.write({"receivable_state": "draft", "receivable_confirm_user_id": False, "receivable_confirm_time": False})
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Receivable"), "message": _("Receivable unconfirmed successfully."), "type": "success",
            "sticky": False, "next": {"type": "ir.actions.client", "tag": "soft_reload"},
        }}

    def action_inbound_remove_from_statement_period(self):
        for rec in self:
            if not rec.statement_period_id:
                continue
            if rec.statement_period_id.state != "draft":
                raise ValidationError(_("Inbound orders cannot be removed after the statement period is confirmed."))
            rec.write({"statement_period_id": False})
        return True


class InboundOrderCharge(models.Model):
    _inherit = "world.depot.inbound.order.charge"

    manual_amount_total = fields.Monetary(string="Manual Amount", currency_field="currency_id", default=0.0)
    charge_billing_object = fields.Selection([("fixed", "Fixed"), ("carton", "Carton"), ("pallet", "Pallet")], string="Billing Object", copy=False)
    quotation_id = fields.Many2one("charge.quotation", string="Quotation", readonly=True, index=True, copy=False, ondelete="restrict")
    quotation_line_id = fields.Many2one("charge.quotation.line", string="Quotation Line", readonly=True, index=True, copy=False, ondelete="restrict")
    is_import_quotation_charge = fields.Boolean(string="Imported Quotation Charge", default=False, readonly=True, copy=False, index=True)
    is_warehouse_operation_charge = fields.Boolean(string="Warehouse Operation Charge", default=False, index=True, copy=False)
    vas_order_id = fields.Many2one("wd.vas.order", string="Warehouse Work Order", readonly=True, index=True, copy=False, ondelete="restrict")
    vas_order_line_id = fields.Many2one("wd.vas.order.line", string="Warehouse Work Order Line", readonly=True, index=True, copy=False, ondelete="restrict")

    @api.depends("quantity", "unit_price", "manual_amount_total")
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.manual_amount_total if rec.manual_amount_total > 0 else (rec.quantity or 0.0) * (rec.unit_price or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        inbound_order_ids = [values.get("inbound_order_id") for values in vals_list if values.get("inbound_order_id")]
        inbound_orders = self.env["world.depot.inbound.order"].browse(inbound_order_ids).exists()
        if inbound_orders.filtered(lambda rec: rec.receivable_state == "confirmed"):
            raise ValidationError(_("Confirmed receivable charge lines cannot be changed."))
        return super().create(vals_list)

    def write(self, vals):
        for rec in self:
            if rec.inbound_order_id.receivable_state == "confirmed":
                raise ValidationError(_("Confirmed receivable charge lines cannot be changed."))
        if vals.get("inbound_order_id"):
            inbound_order = self.env["world.depot.inbound.order"].browse(vals["inbound_order_id"]).exists()
            if inbound_order.receivable_state == "confirmed":
                raise ValidationError(_("Confirmed receivable charge lines cannot be changed."))
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.inbound_order_id.receivable_state == "confirmed":
                raise ValidationError(_("Confirmed receivable charge lines cannot be changed."))
        return super().unlink()

