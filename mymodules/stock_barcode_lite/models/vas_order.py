# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class VasOrder(models.Model):
    _inherit = 'wd.vas.order'

    order_type = fields.Selection([('inbound', 'Inbound'), ('outbound', 'Outbound'), ('transfer', 'Transfer')], string='Warehouse Order Type', tracking=True, copy=False, index=True)
    inbound_order_id = fields.Many2one('world.depot.inbound.order', string='Inbound Order', ondelete='restrict', tracking=True, copy=False, index=True)
    outbound_order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', ondelete='restrict', tracking=True, copy=False, index=True)
    transfer_order_id = fields.Many2one('world.depot.transfer.order', string='Transfer Order', ondelete='restrict', tracking=True, copy=False, index=True)
    warehouse_order_billno = fields.Char(string='Warehouse Order Bill No.', copy=False, index=True)
    _RELATION_BY_ORDER_TYPE = {'inbound': ('inbound_order_id', 'world.depot.inbound.order'), 'outbound': ('outbound_order_id', 'world.depot.outbound.order'), 'transfer': ('transfer_order_id', 'world.depot.transfer.order')}
    _NORMAL_PROTECTED_FIELDS = frozenset({'order_type', 'inbound_order_id', 'outbound_order_id', 'transfer_order_id', 'warehouse_order_billno'})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('order_type'):
                vals.setdefault('source_type', vals['order_type'])
            if vals.get('warehouse_order_billno'):
                vals.setdefault('source_document_number', vals['warehouse_order_billno'].strip())
        return super().create(vals_list)

    @api.onchange('order_type', 'warehouse_order_billno')
    def onchange_warehouse_order_billno(self):
        for rec in self:
            relation = rec._RELATION_BY_ORDER_TYPE.get(rec.order_type)
            billno = (rec.warehouse_order_billno or '').strip()
            rec.source_type = rec.order_type or 'manual'
            rec.source_document_number = billno or False
            rec.source_model = False
            rec.source_record_id = False
            rec.source_document_name = False
            rec.source_picking_id = False
            if not relation or not billno:
                rec.project_id = False
                rec.warehouse_id = False
                continue
            warehouse_orders = rec.env[relation[1]].sudo().search([('billno', '=', billno)], limit=2)
            if len(warehouse_orders) == 1:
                warehouse_order = warehouse_orders
                rec.project_id = warehouse_order.project
                rec.warehouse_id = warehouse_order.warehouse
                rec.source_model = warehouse_order._name
                rec.source_record_id = warehouse_order.id
                rec.source_document_name = warehouse_order.display_name
                rec.source_picking_id = rec.get_source_picking(warehouse_order)
            else:
                rec.project_id = False
                rec.warehouse_id = False

    @api.onchange('order_type', 'inbound_order_id', 'outbound_order_id', 'transfer_order_id')
    def onchange_warehouse_order_relation(self):
        relation_fields = tuple(item[0] for item in self._RELATION_BY_ORDER_TYPE.values())
        for rec in self:
            relation = rec._RELATION_BY_ORDER_TYPE.get(rec.order_type)
            rec.source_type = rec.order_type or 'manual'
            if not relation:
                for field_name in relation_fields:
                    rec[field_name] = False
                continue
            relation_field = relation[0]
            for field_name in relation_fields:
                if field_name != relation_field:
                    rec[field_name] = False
            warehouse_order = rec[relation_field]
            if warehouse_order:
                rec.warehouse_order_billno = warehouse_order.billno
                rec.project_id = warehouse_order.project
                rec.warehouse_id = warehouse_order.warehouse
                rec.source_model = warehouse_order._name
                rec.source_record_id = warehouse_order.id
                rec.source_document_number = warehouse_order.billno
                rec.source_document_name = warehouse_order.display_name
                rec.source_picking_id = rec.get_source_picking(warehouse_order)

    def lock_warehouse_order(self, warehouse_order):
        self.env.cr.execute('SELECT id FROM "%s" WHERE id = %%s FOR UPDATE' % warehouse_order._table, [warehouse_order.id])
        warehouse_order.invalidate_recordset(['state', 'billno', 'warehouse', 'project'])
        return warehouse_order

    def get_warehouse_order(self):
        for rec in self:
            relation = rec._RELATION_BY_ORDER_TYPE.get(rec.order_type)
            if not relation:
                raise ValidationError('Warehouse Order type is invalid.')
            billno = (rec.warehouse_order_billno or '').strip()
            if not billno:
                raise ValidationError('Warehouse Order bill number is required.')
            if billno != rec.warehouse_order_billno:
                rec.action_write({'warehouse_order_billno': billno})
            warehouse_orders = rec.env[relation[1]].sudo().search([('billno', '=', billno)])
            if not warehouse_orders:
                raise ValidationError('No Warehouse Order was found for the specified type and bill number.')
            if len(warehouse_orders) > 1:
                raise ValidationError('More than one Warehouse Order matches the specified type and bill number.')
            return rec.lock_warehouse_order(warehouse_orders)

    def get_source_picking(self, warehouse_order):
        picking = self.env['stock.picking']
        if 'stock_picking_id' in warehouse_order._fields:
            picking = warehouse_order.stock_picking_id
        if not picking and 'picking_PICK' in warehouse_order._fields:
            picking = warehouse_order.picking_PICK
        if not picking and 'picking_Out' in warehouse_order._fields:
            picking = warehouse_order.picking_Out
        return picking

    def get_source_submit_values(self):
        for rec in self:
            if rec.order_type not in rec._RELATION_BY_ORDER_TYPE:
                return super().get_source_submit_values()
            warehouse_order = rec.get_warehouse_order()
            if warehouse_order.state == 'cancel':
                raise ValidationError('A cancelled Warehouse Order cannot be submitted.')
            if not warehouse_order.warehouse:
                raise ValidationError('The linked Warehouse Order has no warehouse configured and cannot be submitted.')
            if rec.project_id != warehouse_order.project:
                raise ValidationError('VAS Order Project must match the Warehouse Order Project.')
            relation_field = rec._RELATION_BY_ORDER_TYPE[rec.order_type][0]
            return {'source_type': rec.order_type, 'source_model': warehouse_order._name, 'source_record_id': warehouse_order.id, 'source_document_number': warehouse_order.billno, 'source_document_name': warehouse_order.display_name, 'source_picking_id': rec.get_source_picking(warehouse_order).id, 'warehouse_order_billno': warehouse_order.billno, 'warehouse_id': warehouse_order.warehouse.id, 'inbound_order_id': False, 'outbound_order_id': False, 'transfer_order_id': False, relation_field: warehouse_order.id}
        return super().get_source_submit_values()

    def get_outbound_palletization_pickings(self):
        picking_model = self.env['stock.picking']
        outbound_order_model = self.env['world.depot.outbound.order']
        pickings = picking_model
        for rec in self:
            if rec.order_type != 'outbound':
                raise UserError(_('Outbound palletization requires this VAS Order to be bound to an outbound order.'))
            outbound_order = rec.outbound_order_id
            if not outbound_order:
                billno = (rec.warehouse_order_billno or '').strip()
                outbound_order_ids = outbound_order_model.sudo().search([('billno', '=', billno)], limit=2).ids if billno else []
                if len(outbound_order_ids) != 1:
                    raise UserError(_('Outbound palletization requires one valid bound outbound order.'))
                outbound_order = outbound_order_model.browse(outbound_order_ids)
            if rec.project_id and rec.project_id != outbound_order.project:
                raise UserError(_('VAS Order Project must match the outbound order Project.'))
            if rec.state == 'draft':
                rec.write({
                    'outbound_order_id': outbound_order.id,
                    'source_type': 'outbound',
                    'source_model': outbound_order._name,
                    'source_record_id': outbound_order.id,
                    'source_document_number': outbound_order.billno,
                    'source_document_name': outbound_order.display_name,
                    'source_picking_id': rec.get_source_picking(outbound_order).id,
                    'project_id': outbound_order.project.id,
                    'warehouse_id': outbound_order.warehouse.id,
                })
            picking_ids = picking_model.sudo().search([('outbound_order_id', '=', outbound_order.id), ('picking_type_id.code', '=', 'outgoing'), ('state', 'not in', ('done', 'cancel'))], order='id').ids
            pickings |= picking_model.browse(picking_ids)
        return pickings

    def write(self, vals):
        values = dict(vals)
        if values.get('order_type'):
            values['source_type'] = values['order_type']
        if 'warehouse_order_billno' in values:
            values['source_document_number'] = (values['warehouse_order_billno'] or '').strip() or False
        for rec in self:
            if rec.state in ('submitted', 'cancelled') and self._NORMAL_PROTECTED_FIELDS.intersection(values):
                raise ValidationError('Submitted or Cancelled VAS Orders cannot be modified.')
        return super().write(values)

    @api.constrains('order_type', 'inbound_order_id', 'outbound_order_id', 'transfer_order_id')
    def check_order_relation_consistency(self):
        relation_fields = tuple(item[0] for item in self._RELATION_BY_ORDER_TYPE.values())
        for rec in self:
            populated = [field_name for field_name in relation_fields if rec[field_name]]
            if len(populated) > 1:
                raise ValidationError('Only one Warehouse Order relation may be set.')
            expected_field = rec._RELATION_BY_ORDER_TYPE.get(rec.order_type, (False,))[0]
            if populated and populated[0] != expected_field:
                raise ValidationError('Warehouse Order relation must match the selected order type.')
