# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ContainerServiceRequest(models.Model):
    _name = 'container.service.request'
    _description = 'Container Service Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(string='Request No.', required=True, copy=False,
                       default=lambda self: _('New'))

    request_type = fields.Selection([
        ('depot_to_warehouse', 'Depot / Terminal → Warehouse'),
        ('warehouse_to_depot', 'Warehouse → Depot / Terminal'),
    ], string='Direction', required=True, default='depot_to_warehouse')

    container_master_id = fields.Many2one('container.master', string='Container Record')
    container_number = fields.Char(string='Container No.', required=True)
    container_type = fields.Selection([
        ('20GP', '20GP'), ('40GP', '40GP'), ('40HQ', '40HQ'),
        ('40HC', '40HC'), ('45HQ', '45HQ'),
    ], string='Container Type', required=True, default='20GP')
    quantity = fields.Integer(string='Quantity', default=1)

    depot_location_id = fields.Many2one(
        'res.partner', string='Depot / Terminal',
        domain=[('is_company', '=', True)])
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse')

    carrier_id = fields.Many2one(
        'res.partner', string='Trucking Company',
        domain=[('is_carrier', '=', True)])
    planned_date = fields.Date(string='Planned Date')

    driver_name = fields.Char(string='Driver Name')
    driver_phone = fields.Char(string='Driver Phone')
    vehicle_plate = fields.Char(string='Vehicle Plate')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)

    @api.onchange('container_master_id')
    def _onchange_container_master_id(self):
        if self.container_master_id:
            self.container_number = self.container_master_id.container_number
            self.container_type = self.container_master_id.container_type

    transport_order_id = fields.Many2one(
        'tlmp.transport.order', string='Dispatch Order',
        readonly=True, copy=False)
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        for r in self:
            if r.container_master_id:
                master = r.container_master_id
                master.write({'active': True})
                self.env['container.master.history.line'].create({
                    'master_id': master.id,
                    'reference_type': 'container_service_request',
                    'reference_id': r.id,
                    'direction': 'outbound' if r.request_type == 'warehouse_to_depot' else 'inbound',
                    'location_start': r.depot_location_id.name if r.depot_location_id else False,
                    'location_end': r.warehouse_id.name if r.warehouse_id else False,
                    'remark': 'Empty container repositioning',
                })
        return True

    def action_complete(self):
        self.write({'state': 'completed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_create_transport_order(self):
        self.ensure_one()
        if self.transport_order_id:
            return self._open_order()
        if self.state != 'confirmed':
            raise UserError(_('Only confirmed requests can create dispatch orders.'))

        type_map = {
            'depot_to_warehouse': 'port_to_warehouse',
            'warehouse_to_depot': 'to_customer',
        }
        order = self.env['tlmp.transport.order'].create({
            'partner_id': self.carrier_id.id or self.env.user.partner_id.id,
            'carrier_id': self.carrier_id.id,
            'transport_type_id': self.env['tlmp.transport.type']._get_by_code(type_map.get(self.request_type, 'port_to_warehouse')).id,
            'fleet_operation_mode': 'subcontracted',
            'planned_pickup_date': self.planned_date,
            'driver_name': self.driver_name,
            'driver_phone': self.driver_phone,
            'vehicle_plate': self.vehicle_plate,
            'cargo_description': _('Empty container: %s x %s') % (
                self.quantity, self.container_number),
            'notes': self.notes,
        })
        self.env['tlmp.transport.container'].create({
            'order_id': order.id,
            'name': self.container_number,
            'container_type': self.container_type,
        })
        self.transport_order_id = order.id
        return self._open_order()

    def _open_order(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tlmp.transport.order',
            'view_mode': 'form',
            'res_id': self.transport_order_id.id,
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'container.service.request.seq') or _('New')
        return super().create(vals_list)
