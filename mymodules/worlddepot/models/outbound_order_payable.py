# -*- coding: utf-8 -*-

from odoo import api, fields, models


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    payable_lines = fields.One2many("world.depot.outbound.order.payable", "outbound_order_id", string="Payables", copy=False)


class OutboundOrderPayable(models.Model):
    _name = "world.depot.outbound.order.payable"
    _description = "Outbound Order Payable"
    _order = "id desc"

    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", required=True, ondelete="cascade", index=True, copy=False)
    vendor_partner_id = fields.Many2one("res.partner", string="Vendor", required=True, ondelete="restrict", index=True)
    vendor_invoice_num = fields.Char(string="Vendor Invoice No")
    payable_date = fields.Date(string="Payable Date", required=True, default=fields.Date.context_today, index=True)
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, index=True, default=lambda self: self.default_currency_id())
    amount_total = fields.Monetary(string="Total Amount", currency_field="currency_id", compute="_compute_amount_total", store=True)
    charge_lines = fields.One2many("world.depot.outbound.order.payable.charge", "payable_id", string="Charge Lines", copy=False)
    remark = fields.Text(string="Remark")

    @api.model
    def default_currency_id(self):
        outbound_order_id = self.env.context.get("default_outbound_order_id")
        if outbound_order_id:
            outbound_order = self.env["world.depot.outbound.order"].sudo().browse(outbound_order_id)
            if outbound_order.currency_id:
                return outbound_order.currency_id.id
        return self.env.company.currency_id.id

    @api.depends("charge_lines.amount")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(line.amount for line in rec.charge_lines)


class OutboundOrderPayableCharge(models.Model):
    _name = "world.depot.outbound.order.payable.charge"
    _description = "Outbound Order Payable Charge"

    payable_id = fields.Many2one("world.depot.outbound.order.payable", string="Payable", required=True, ondelete="cascade", index=True, copy=False)
    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", required=True, index=True, ondelete="restrict")
    quantity = fields.Float(string="Quantity", required=True, default=1.0)

    charge_unit_id = fields.Many2one("world.depot.charge.unit", string="Unit")
    unit_price = fields.Monetary(string="Unit Price", required=True, default=0.0)
    amount = fields.Monetary(string="Amount", currency_field="currency_id", compute="_compute_amount", store=True)
    currency_id = fields.Many2one("res.currency", string="Currency", related="payable_id.currency_id", store=True, readonly=True, index=True)
    remark = fields.Text(string="Remark")

    @api.depends("quantity", "unit_price")
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.quantity or 0.0) * (rec.unit_price or 0.0)
