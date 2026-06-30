# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import json
from odoo.addons.wd_iffm.models.charge_item_inherit import TAB_CATEGORY_LIST,OPERATION_TYPE


class OperationOrderHandoverChargeLine(models.Model):
    _name = "operation.order.handover.charge.line"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Charge Line (AR)"
    _order = "id desc"

    handover_id = fields.Many2one("operation.order.handover", string="Handover", required=True, ondelete="cascade", index=True)
    container_qty = fields.Integer(string="Container Qty", compute="compute_container_qty", store=True)
    @api.depends("handover_id.container_qty")
    def compute_container_qty(self):
        for rec in self:
            if rec.handover_id:
                rec.container_qty = rec.handover_id.container_qty

    charge_origin_type = fields.Selection([("quotation", "Quotation"), ("manual", "Manual")], string="Charge Source", default="manual", required=True)
    quotation_id = fields.Many2one("charge.quotation", string="Quotation",related="handover_id.waybill_id.quotation_id", store=True,
                                   readonly=True, index=True)
    project_id = fields.Many2one("project.project", string="Project/Customer",related="handover_id.project_id", store=True, readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", related="handover_id.waybill_id.quotation_id.currency_id", store=True, readonly=True)

    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item",tracking= True)
    quotation_tab_category = fields.Selection(TAB_CATEGORY_LIST,related="charge_item_id.tab_category", string="Tab Category",tracking= True)
    charge_item_operation_type = fields.Selection(OPERATION_TYPE, string="Operation Type", related="charge_item_id.operation_type", store=True)
    #rule_id = fields.Many2one("charge.rule", string="Charge Rule",tracking= True)
    #quantity_rule_id = fields.Many2one("charge.quantity.rule", string="Quantity Rule",tracking= True)
    is_fixed_fee = fields.Boolean(string="Fixed Fee", default=False, index=True)
    qty = fields.Float(string="Qty", default=1.0,tracking= True, store=True)
    unit_price = fields.Monetary(string="Unit Price", currency_field="currency_id", default=0.0,tracking= True)
    amount_total = fields.Monetary(string="Total Amount", currency_field="currency_id", compute="compute_amount_total")
    unit_id = fields.Many2one("world.depot.charge.unit", string="Unit", related="charge_item_id.unit_id", store=True)
    manual_amount_total = fields.Monetary(string="Manual Total Amount", currency_field="currency_id", default=0.0,
                                          tracking=True)
    # rule_snapshot = fields.Text(string="Rule Snapshot")
    # source_snapshot = fields.Text(string="Source Snapshot")
    remark = fields.Char(string="Remark")



    @api.depends("qty", "unit_price", "is_fixed_fee")
    def compute_amount_total(self):
        for rec in self:
            if rec.is_fixed_fee:
                rec.amount_total = rec.unit_price or 0.0
            else:
                rec.amount_total = (rec.qty or 0.0) * (rec.unit_price or 0.0)

    @api.onchange("charge_item_id")
    def onchange_charge_item_id(self):
        for rec in self:
            if not rec.charge_item_id or not rec.handover_id:
                continue
            all_lines = rec.handover_id.charge_line_ids
            other_lines = []
            for line in all_lines:
                if rec.id and line.id:
                    if line.id != rec.id:
                        other_lines.append(line)
                else:
                    if line != rec:
                        other_lines.append(line)
            for line in other_lines:
                if line.charge_item_id and line.charge_item_id.id == rec.charge_item_id.id:
                    raise ValidationError(_("Charge item already exists in this handover."))

    # SOURCE_FIELDS = ("handover_id",)
    #
    # @api.depends(*SOURCE_FIELDS)
    # def compute_project_currency(self):
    #     for rec in self:
    #         source = False
    #         for field in self.SOURCE_FIELDS:
    #             value = getattr(rec, field, False)
    #             if value:
    #                 source = value
    #                 break
    #         rec.project_id = source.project_id.id if source and source.project_id else False
    #         rec.currency_id = source.currency_id.id if source and source.currency_id else False
    #         rec.quotation_id = source.waybill_id.quotation_id.id if source and source.waybill_id.quotation_id else False
    # # 计算单价
    # @api.depends("charge_item_id","quotation_id","rule_id","rule_id.price_source")
    # def compute_price_unit(self):
    #     quotation_line_model = self.env["charge.quotation.line"].sudo()
    #     for rec in self:
    #         source = False
    #         for field in self.SOURCE_FIELDS:
    #             value = getattr(rec, field, False)
    #             if value:
    #                 source = value
    #                 break
    #         if source.state == 'close':
    #              continue
    #         if rec.is_manual_unit_price:
    #             rec.unit_price = rec.manual_unit_price
    #             continue
    #         price = 0.0
    #         if not rec.rule_id:
    #             rec.unit_price = price
    #             continue
    #         if rec.rule_id.price_source == "quotation":
    #             quotation_line = quotation_line_model.search(
    #                 [("quotation_id", "=", rec.quotation_id.id), ("charge_item_id", "=", rec.charge_item_id.id),("active", "=", True)],
    #                 limit=1)
    #             price = quotation_line.unit_price if quotation_line else 0.0
    #
    #         elif rec.rule_id.price_source == "from_rule":
    #             price = rec.rule_id.unit_price or 0.0
    #         rec.unit_price = price
    #
    # @api.depends("quantity_rule_id",*SOURCE_FIELDS,'container_qty')
    # def compute_quantity(self):
    #     for rec in self:
    #         source = False
    #         for field in self.SOURCE_FIELDS:
    #             value = getattr(rec, field, False)
    #             if value:
    #                 source = value
    #                 break
    #         if source.state == 'close':
    #              continue
    #         if not rec.quantity_rule_id:
    #             rec.qty= 1.0
    #             continue
    #         qty, _snap = rec.compute_quantity_by_rule()
    #         rec.qty = qty
    #
    # # 计算 单行总价
    # @api.depends("qty","unit_price","rule_id","rule_id.pricing_type",)
    # def compute_amount_total(self):
    #     for rec in self:
    #         source = False
    #         for field in self.SOURCE_FIELDS:
    #             value = getattr(rec, field, False)
    #             if value:
    #                 source = value
    #                 break
    #         if source.state == 'close':
    #             continue
    #         if not rec.rule_id:
    #             rec.amount_total = 0.0
    #             continue
    #
    #         qty = rec.qty or 0.0
    #         price = rec.unit_price or 0.0
    #
    #         if rec.rule_id.pricing_type == "fixed":
    #             rec.amount_total = rec.rule_id.fixed_amount or 0.0
    #         elif rec.rule_id.pricing_type == "unit_x_qty":
    #             amount = price * qty
    #             rec.amount_total = amount
    #
    #
    # def compute_quantity_by_rule(self):
    #     self.ensure_one()
    #     source = False
    #     for field in self.SOURCE_FIELDS:
    #         value = getattr(self, field, False)
    #         if value:
    #             source = value
    #
    #     code = self.quantity_rule_id.code
    #     qty = 1.0
    #     snap = {"quantity_rule": self.quantity_rule_id.name, "code": code}
    #
    #     if code == "by_order":
    #         qty = 1.0
    #         snap["logic"] = "by_order => 1"
    #     elif code == "by_container":
    #
    #         container_qty = getattr(source, "container_qty", 0) or 0
    #         qty = float(container_qty)
    #         snap["logic"] = "by_container => source.container_qty"
    #         snap["container_qty"] = container_qty
    #     elif code == "by_hs":
    #         hs_total = getattr(source, "hs_total", 0) or 0
    #         qty = float(hs_total)
    #         snap["logic"] = "by_hs => source.hs_total"
    #         snap["hs_total"] = hs_total
    #
    #     if qty <= 0:
    #         qty = 1.0
    #         snap["fallback"] = "qty<=0 fallback to 1"
    #
    #     return qty, snap

