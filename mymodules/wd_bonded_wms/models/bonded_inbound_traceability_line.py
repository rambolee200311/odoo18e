# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class BondedInboundTraceabilityLine(models.Model):
    _name = 'bonded.inbound.traceability.line'
    _description = 'Bonded Inbound Traceability Line'
    _order = 'inbound_line_id, id'

    inbound_line_id = fields.Many2one('bonded.inbound.line', string='Inbound Product Line', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, ondelete='restrict', index=True)
    lot_name = fields.Char(string='Lot/SN', required=True, copy=False, index=True)
    planned_qty = fields.Float(string='Planned Qty', required=True, default=1.0)

    _sql_constraints = [
        ('inbound_line_lot_name_uniq', 'unique(inbound_line_id, lot_name)', 'The same lot or serial number cannot be repeated on one inbound product line.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        env_inbound_line = self.env['bonded.inbound.line'].sudo()
        for vals in vals_list:
            inbound_line = env_inbound_line.browse(vals.get('inbound_line_id')).exists()
            if inbound_line:
                vals.setdefault('product_id', inbound_line.product_id.id)
        return super().create(vals_list)

    @api.constrains('inbound_line_id', 'product_id', 'lot_name', 'planned_qty')
    def check_traceability_values(self):
        env_traceability_line = self.env['bonded.inbound.traceability.line'].sudo()
        for rec in self:
            if not rec.inbound_line_id or not rec.product_id:
                continue
            if rec.product_id != rec.inbound_line_id.product_id:
                raise ValidationError(_('The traceability line product must match the inbound product line.'))
            rounding = rec.product_id.uom_id.rounding
            if float_compare(rec.planned_qty, 0.0, precision_rounding=rounding) <= 0:
                raise ValidationError(_('The lot/SN planned quantity must be greater than zero.'))
            if rec.product_id.tracking == 'none':
                raise ValidationError(_('Lot/SN details are only allowed for products with lot or serial tracking.'))
            if rec.product_id.tracking == 'serial' and float_compare(rec.planned_qty, 1.0, precision_rounding=rounding) != 0:
                raise ValidationError(_('The planned quantity of a serial number must be 1.'))
            traceability_lines = env_traceability_line.search([('inbound_line_id', '=', rec.inbound_line_id.id)])
            total_qty = sum(traceability_lines.mapped('planned_qty'))
            if float_compare(total_qty, rec.inbound_line_id.planned_qty, precision_rounding=rounding) > 0:
                raise ValidationError(_('The total lot/SN planned quantity cannot exceed the inbound product line quantity.'))
