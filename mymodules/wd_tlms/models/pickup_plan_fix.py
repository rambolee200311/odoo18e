# -*- coding: utf-8 -*-
"""Fix pickup.plan to be a sub-document of transport.request.
Sprint3: demote pickup.plan from entry point to plan-driven sub-document.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PickupPlan(models.Model):
    _inherit = 'pickup.plan'

    # -----------------------------------------------------------
    # Override: redirect to parent transport.request
    # -----------------------------------------------------------
    def action_create_transport_request(self):
        """Redirect: pickup.plan is now a sub-document of transport.request.
        Open the parent request instead of creating a new one."""
        self.ensure_one()
        if self.transport_request_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'tlmp.transport.request',
                'view_mode': 'form',
                'res_id': self.transport_request_id.id,
                'target': 'current',
            }
        msg = _(
            'Pickup Plan is a scheduling sub-document under a Transport Request. '
            'Please create a Transport Request first (Operations > Transport Requests), '
            'then schedule via the calendar, which will create Pickup Plans automatically.'
        )
        raise UserError(msg)

    def action_open_parent_request(self):
        """Open the parent transport.request form."""
        self.ensure_one()
        if not self.transport_request_id:
            raise UserError(_('This Pickup Plan is not linked to any Transport Request.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tlmp.transport.request',
            'view_mode': 'form',
            'res_id': self.transport_request_id.id,
            'target': 'current',
        }

    # -----------------------------------------------------------
    # Constraint: transport_request_id required
    # -----------------------------------------------------------
    @api.constrains('transport_request_id')
    def _check_transport_request_id(self):
        for rec in self:
            if not rec.transport_request_id:
                raise UserError(
                    _('Pickup Plan must belong to a Transport Request. '
                      'Create a Transport Request first, then schedule via the calendar.'))

    # -----------------------------------------------------------
    # Override create: ensure transport_request_id
    # -----------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('transport_request_id'):
                # Auto-create a transport request for the plan
                req = self.env['tlmp.transport.request'].create({
                    'request_type': 'plan_driven',
                    'destination_type': vals.get('destination_type', 'warehouse'),
                    'cargo_type': vals.get('cargo_type', 'container'),
                    'cargo_description': vals.get('cargo_description', ''),
                    'pallet_count': vals.get('pallet_count', 0),
                    'package_count': vals.get('package_count', 0),
                    'cargo_weight': vals.get('cargo_weight', 0.0),
                    'cargo_volume': vals.get('cargo_volume', 0.0),
                })
                vals['transport_request_id'] = req.id
        return super().create(vals_list)

    # -----------------------------------------------------------
    # Fix action_create_transport_order to reference parent request
    # -----------------------------------------------------------
    def action_create_transport_order(self):
        self.ensure_one()
        if self.transport_order_id:
            return self._open_record('tlmp.transport.order', self.transport_order_id.id)
        if self.destination_type not in ('warehouse', 'warehouse_transfer'):
            raise UserError(_('Direct order creation is only for warehouse / warehouse transfer destinations.'))
        if self.cargo_type == 'container' and not self.container_line_ids:
            raise UserError(_('No container lines. Please add at least one container.'))
        if not self.carrier_id and self.transport_request_id and self.transport_request_id.carrier_id:
            self.carrier_id = self.transport_request_id.carrier_id
        if not self.carrier_id:
            raise UserError(_('Please select a Trucking Company.'))

        type_map = {'warehouse': 'port_to_warehouse', 'warehouse_transfer': 'warehouse_transfer'}
        tr_type = type_map.get(self.destination_type, 'port_to_warehouse')
        order_vals = {
           'pickup_plan_id': self.id,
            'scene_id': self.scene_id.id or (self.transport_request_id.scene_id.id if self.transport_request_id else False),
            'transport_type_id': self.env['tlmp.transport.type']._get_by_code(tr_type).id,
            'fleet_operation_mode': 'subcontracted',
            'partner_id': (self.partner_id.id or
                           (self.transport_request_id.partner_id.id if self.transport_request_id else False) or
                           self.env.company.partner_id.id),
            'carrier_id': self.carrier_id.id,
            'cargo_description': self.cargo_description or (_('Pickup plan %s') % self.name),
            'cargo_weight': self.cargo_weight, 'cargo_volume': self.cargo_volume,
            'pallet_count': self.pallet_count, 'package_count': self.package_count,
            'planned_pickup_date': self.planned_pickup_date or self.scheduled_date,
            'driver_name': self.driver_name, 'driver_phone': self.driver_phone,
            'vehicle_plate': self.vehicle_plate, 'notes': self.notes,
        }
        if self.transport_request_id:
            order_vals['request_id'] = self.transport_request_id.id
        # Sprint44/45: copy address snapshot from plan
        order_vals.update({
            'origin_street': self.origin_street,
            'origin_zip': self.origin_zip,
            'origin_city': self.origin_city,
            'origin_state_id': self.origin_state_id.id if self.origin_state_id else False,
            'origin_country_id': self.origin_country_id.id if self.origin_country_id else False,
            'destination_street': self.destination_street,
            'destination_zip': self.destination_zip,
            'destination_city': self.destination_city,
            'destination_state_id': self.destination_state_id.id if self.destination_state_id else False,
            'destination_country_id': self.destination_country_id.id if self.destination_country_id else False,
            'place_of_departure': ', '.join(x for x in (self.origin_street or '', self.origin_zip or '', self.origin_city or '') if x),
            'place_of_destination': ', '.join(x for x in (self.destination_street or '', self.destination_zip or '', self.destination_city or '') if x),
        })
        if self.destination_type == 'warehouse_transfer':
            order_vals['pickup_location_id'] = (
                self.source_warehouse_id.partner_id.id if self.source_warehouse_id else False)
            order_vals['delivery_location_id'] = (
                self.warehouse_id.partner_id.id if self.warehouse_id else False)
        else:
            order_vals['delivery_location_id'] = (
                self.warehouse_id.partner_id.id if self.warehouse_id else False)
            if self.terminal_id:
                order_vals['pickup_location_id'] = self.terminal_id.id

        order = self.env['tlmp.transport.order'].create(order_vals)
        for cl in self.container_line_ids:
            self.env['tlmp.transport.container'].create({
                'order_id': order.id, 'name': cl.container_number,
                'container_type': cl.container_type, 'seal_number': cl.seal_number,
                'cargo_weight_kg': cl.weight,
                'container_master_id': cl.container_master_id.id if cl.container_master_id else False,
            })

        # Create fee.line (carrier cost) for plan-driven flow
        charge_item = self.env['world.depot.charge.item'].search([], limit=1)
        if charge_item and self.carrier_id:
            self.env['transport.fee.line'].create({
                'fee_type_id': charge_item.id,
                'source_type': 'plan_driven',
                'source_order_id': order.id,
                'party_type': 'carrier_cost',
                'partner_id': self.carrier_id.id,
                'quantity': 1.0,
                'unit_amount': 0.0,
                'description': 'Transport cost - %s' % self.name,
            })

        self.transport_order_id = order.id
        return self._open_record('tlmp.transport.order', order.id)

    def _open_record(self, model, res_id):
        return {'type': 'ir.actions.act_window', 'res_model': model,
                'view_mode': 'form', 'res_id': res_id, 'target': 'current'}
