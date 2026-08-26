# -*- coding: utf-8 -*-

from odoo import fields, models


class InboundOrder(models.Model):
    _inherit = 'world.depot.inbound.order'

    stock_operation_portal_confirmed = fields.Boolean(string='Portal Confirmed', readonly=True, copy=False, index=True, tracking=True)
    stock_operation_portal_confirm_user_id = fields.Many2one('res.users', string='Portal Confirmed By', readonly=True, copy=False, tracking=True)
    stock_operation_portal_confirm_time = fields.Datetime(string='Portal Confirmed At', readonly=True, copy=False, tracking=True)
