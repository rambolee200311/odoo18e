# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class VasOrder(models.Model):
    _inherit = 'wd.vas.order'

    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', readonly=True, copy=False, ondelete='restrict', index=True)
    bonded_outbound_id = fields.Many2one('bonded.outbound', string='Bonded Outbound', readonly=True, copy=False, ondelete='restrict', index=True)
    _BONDED_SOURCE_MODELS = {'bonded_inbound': ('bonded.inbound', 'bonded_inbound_id'), 'bonded_outbound': ('bonded.outbound', 'bonded_outbound_id')}
    _BONDED_PROTECTED_FIELDS = frozenset({'bonded_inbound_id', 'bonded_outbound_id'})

    def get_source_submit_values(self):
        for rec in self:
            source_definition = rec._BONDED_SOURCE_MODELS.get(rec.source_type)
            if not source_definition:
                return super().get_source_submit_values()
            model_name, relation_field = source_definition
            if rec.source_model != model_name or not rec.source_record_id:
                raise ValidationError('The bonded VAS source is invalid.')
            source = rec.env[model_name].sudo().browse(rec.source_record_id).exists()
            if not source:
                raise ValidationError('The bonded VAS source no longer exists.')
            rec.env.cr.execute('SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % source._table, [source.id])
            source.invalidate_recordset(['state', 'name', 'project_id', 'warehouse', 'picking_id'])
            if source.state == 'cancelled':
                raise ValidationError('A cancelled bonded instruction cannot be submitted.')
            if not source.warehouse:
                raise ValidationError('The bonded instruction has no warehouse configured and cannot be submitted.')
            if rec.project_id != source.project_id:
                raise ValidationError('VAS Order Project must match the bonded instruction Project.')
            return {'source_type': rec.source_type, 'source_model': model_name, 'source_record_id': source.id, 'source_document_number': source.name, 'source_document_name': source.display_name, 'source_picking_id': source.picking_id.id, 'project_id': source.project_id.id, 'warehouse_id': source.warehouse.id, 'bonded_inbound_id': False, 'bonded_outbound_id': False, relation_field: source.id}
        return super().get_source_submit_values()

    def write(self, vals):
        for rec in self:
            if rec.state in ('submitted', 'cancelled') and self._BONDED_PROTECTED_FIELDS.intersection(vals):
                raise ValidationError('Submitted or Cancelled VAS Orders cannot be modified.')
        return super().write(vals)


class BondedInbound(models.Model):
    _inherit = 'bonded.inbound'

    def action_create_vas_order(self):
        order_values = []
        for rec in self:
            order_values.append({'source_type': 'bonded_inbound', 'source_model': rec._name, 'source_record_id': rec.id, 'source_document_number': rec.name, 'source_document_name': rec.display_name, 'source_picking_id': rec.picking_id.id, 'project_id': rec.project_id.id, 'warehouse_id': rec.warehouse.id, 'bonded_inbound_id': rec.id})
        vas_orders = self.env['wd.vas.order'].create(order_values)
        action = self.env.ref('wd_warehouse_value_add.action_vas_order').sudo().read()[0]
        action['domain'] = [('id', 'in', vas_orders.ids)]
        if len(vas_orders) == 1:
            action.update({'view_mode': 'form', 'res_id': vas_orders.id})
        return action


class BondedOutbound(models.Model):
    _inherit = 'bonded.outbound'

    def action_create_vas_order(self):
        order_values = []
        for rec in self:
            order_values.append({'source_type': 'bonded_outbound', 'source_model': rec._name, 'source_record_id': rec.id, 'source_document_number': rec.name, 'source_document_name': rec.display_name, 'source_picking_id': rec.picking_id.id, 'project_id': rec.project_id.id, 'warehouse_id': rec.warehouse.id, 'bonded_outbound_id': rec.id})
        vas_orders = self.env['wd.vas.order'].create(order_values)
        action = self.env.ref('wd_warehouse_value_add.action_vas_order').sudo().read()[0]
        action['domain'] = [('id', 'in', vas_orders.ids)]
        if len(vas_orders) == 1:
            action.update({'view_mode': 'form', 'res_id': vas_orders.id})
        return action
