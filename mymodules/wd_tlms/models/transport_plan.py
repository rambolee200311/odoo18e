# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TransportPlan(models.Model):
    """Unified transport plan abstraction (Sprint50-A A1)."""

    _name = 'tlmp.transport.plan'
    _description = 'Transport Plan Abstraction'
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(string='Plan No.', required=True,
                       default=lambda self: _('New'))
    plan_type = fields.Selection([
        ('pickup', 'Pickup Plan'),
        ('container', 'Container Plan'),
    ], string='Plan Type', default='pickup')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('reserved', 'Reserved'),
        ('executing', 'Executing'),
        ('finished', 'Finished'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')
    reservation_type = fields.Selection([
        ('vehicle', 'Vehicle'),
        ('driver', 'Driver'),
        ('carrier_capacity', 'Carrier Capacity'),
    ], string='Reservation Type', default='vehicle')
    vehicle_allocation_snapshot = fields.Text(
        string='Vehicle Allocation Snapshot')
    allocation_candidate = fields.Text(
        string='Allocation Candidate',
        help='JSON draft produced by plan.reserve validation (not a model).')
    allocation_candidate_valid = fields.Boolean(
        string='Allocation Candidate Valid', default=False)
    assignment_context = fields.Text(string='Assignment Context')
    transport_request_id = fields.Many2one(
        'tlmp.transport.request', string='Transport Request')
    pickup_plan_id = fields.Many2one(
        'pickup.plan', string='Pickup Plan', ondelete='cascade')
    container_plan_id = fields.Many2one(
        'container.transport.plan', string='Container Plan',
        ondelete='cascade')


class BlContainer(models.Model):
    _name = 'bl.container'
    _description = 'Container'
    _order = 'id desc'

    bl_no = fields.Char(string='BL No.', index=True)
    container_no = fields.Char(string='Container No.', required=True, index=True)
    container_type = fields.Selection([
        ('20GP', '20GP'), ('40GP', '40GP'), ('40HQ', '40HQ'),
        ('40HC', '40HC'), ('45HQ', '45HQ'), ('OT', 'OT'),
        ('FR', 'FR'), ('RF', 'RF'), ('other', 'Other'),
    ], string='Container Type', default='20GP')
    supplier = fields.Char(string='Supplier')
    destination_warehouse = fields.Many2one('stock.warehouse', string='Destination Warehouse')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending')
    plan_ids = fields.One2many('container.transport.plan', 'container_id', string='Schedule Records')
    scheduled = fields.Boolean(string='Scheduled', compute='_compute_scheduled', store=True)

    @api.depends('state')
    def _compute_scheduled(self):
        for r in self:
            r.scheduled = r.state == 'scheduled'

    def get_unplanned_containers(self):
        # Sync from pickup.plan.container.line (pickup plans)
        lines = self.env['pickup.plan.container.line'].search([
            ('container_number', '!=', False)
        ])
        for line in lines:
            existing = self.search([('container_no', '=', line.container_number)], limit=1)
            if not existing:
                plan = line.plan_id
                self.create({
                    'container_no': line.container_number,
                    'container_type': line.container_type or '20GP',
                    'bl_no': line.bl_number or '',
                    'destination_warehouse': plan.warehouse_id.id if plan and plan.warehouse_id else False,
                    'state': 'pending',
                })
        return self.search_read([('state', '!=', 'scheduled')],
            ['id', 'bl_no', 'container_no', 'container_type',
             'supplier', 'destination_warehouse', 'state', 'scheduled'])


class TransportPlan(models.Model):
    _name = 'container.transport.plan'
    _description = 'Transport Schedule Record'
    _order = 'plan_date desc, id desc'

    plan_date = fields.Date(string='Plan Date', required=True, index=True)
    container_id = fields.Many2one('bl.container', string='Container', required=True, ondelete='cascade')
    container_no = fields.Char(string='Container No.', related='container_id.container_no', store=True, readonly=True)
    bl_no = fields.Char(string='BL No.', related='container_id.bl_no', store=True, readonly=True)
    transport_company = fields.Char(string='Trucking Company')
    remark = fields.Text(string='Remark')
    state = fields.Selection(
        related='transport_plan_id.state', readonly=True,
        string='Status (Transport Plan)')
    reservation_type = fields.Selection(
        related='transport_plan_id.reservation_type', readonly=True,
        string='Reservation Type')
    assignment_context = fields.Text(string='Assignment Context')
    vehicle_allocation_snapshot = fields.Text(
        related='transport_plan_id.vehicle_allocation_snapshot', readonly=True,
        string='Vehicle Allocation Snapshot')
    transport_plan_id = fields.Many2one(
        'tlmp.transport.plan', string='Transport Plan Abstraction',
        ondelete='set null')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for idx, rec in enumerate(records):
            if not rec.transport_plan_id:
                raw_state = (vals_list[idx].get('state') or 'draft')
                abstract_state = raw_state
                if abstract_state == 'confirmed':
                    abstract_state = 'reserved'
                elif abstract_state == 'completed':
                    abstract_state = 'finished'
                elif abstract_state not in (
                        'draft', 'scheduled', 'reserved', 'executing',
                        'finished', 'failed', 'cancelled'):
                    abstract_state = 'draft'
                abstract = self.env['tlmp.transport.plan'].create({
                    'name': 'CT-%s' % (rec.container_no or rec.id),
                    'plan_type': 'container',
                    'state': abstract_state,
                    'reservation_type': (
                        vals_list[idx].get('reservation_type') or 'vehicle'),
                    'assignment_context': rec.assignment_context,
                    'container_plan_id': rec.id,
                })
                rec.write({'transport_plan_id': abstract.id})
        return records

    def action_schedule(self):
        self.ensure_one()
        if not self.transport_plan_id or self.transport_plan_id.state != 'draft':
            raise UserError(_('Only draft plans can be scheduled.'))
        self.env['tlmp.workflow.engine'].transition(
            self.transport_plan_id, 'scheduled', 'PLAN_SCHEDULED')
        return True

    def action_reserve(self, reservation_type='vehicle'):
        self.ensure_one()
        if not self.transport_plan_id or self.transport_plan_id.state != 'scheduled':
            raise UserError(_('Only scheduled plans can reserve resources.'))
        req = self.transport_request_id
        abstract = self.transport_plan_id
        if not self.assignment_context:
            raise UserError(_(
                'Assignment context is required before resource reservation.'))
        if req and req.is_dangerous_goods == 'adr_dangerous' \
                and not self.assignment_context:
            raise UserError(_(
                'ADR plan reservation requires assignment_context '
                '(driver_id / driver_adr_valid / expiry_date).'))
        if req and req.vehicle_requirement_mode_snapshot == 'exempted':
            self.env['tlmp.workflow.engine'].transition(
                abstract, 'reserved', 'PLAN_RESERVED',
                event_category='business',
                extra_vals={'reservation_type': reservation_type})
            return True
        abstract.assignment_context = self.assignment_context
        candidate = {
            'valid': True,
            'reservation_type': reservation_type,
            'reserved_carrier_id': self.container_id.supplier or False,
            'reserved_vehicle_plate': self.transport_company or False,
            'assignment_context': self.assignment_context,
        }
        if req:
            candidate.update({
                'vehicle_requirement_mode': (
                    req.vehicle_requirement_mode_snapshot
                    or req.vehicle_requirement_mode),
                'vehicle_body_type': req.vehicle_body_type,
                'vehicle_capacity_requirement':
                    req.vehicle_capacity_requirement,
                'is_dangerous_goods': req.is_dangerous_goods,
            })
        self.env['tlmp.workflow.engine'].transition(
            abstract, 'reserved', 'PLAN_RESERVED',
            event_category='business',
            extra_vals={
                'reservation_type': reservation_type,
                'allocation_candidate': json.dumps(
                    candidate, ensure_ascii=False),
                'allocation_candidate_valid': True,
            },
            payload=json.dumps(candidate, ensure_ascii=False))
        return True

    def action_execute(self):
        self.ensure_one()
        if not self.transport_plan_id or self.transport_plan_id.state != 'reserved':
            raise UserError(_('Only reserved plans can start execution.'))
        self.env['tlmp.workflow.engine'].transition(
            self.transport_plan_id, 'executing', 'PLAN_EXECUTING')
        return True

    def action_finish(self):
        self.ensure_one()
        if not self.transport_plan_id or self.transport_plan_id.state != 'executing':
            raise UserError(_('Only executing plans can be finished.'))
        self.env['tlmp.workflow.engine'].transition(
            self.transport_plan_id, 'finished', 'PLAN_FINISHED')
        return True

    def action_fail(self):
        self.ensure_one()
        if not self.transport_plan_id or self.transport_plan_id.state not in (
                'scheduled', 'reserved', 'executing'):
            raise UserError(_('Plan cannot fail in current state.'))
        self.env['tlmp.workflow.engine'].transition(
            self.transport_plan_id, 'failed', 'PLAN_FAILED')
        return True

    def action_cancel_plan(self):
        self.ensure_one()
        if not self.transport_plan_id or self.transport_plan_id.state in (
                'finished', 'failed', 'cancelled'):
            raise UserError(_('Plan is already in a final state.'))
        self.env['tlmp.workflow.engine'].transition(
            self.transport_plan_id, 'cancelled', 'PLAN_CANCELLED')
        return True

    def create_transport_plan(self, container_id, plan_date):
        container = self.env['bl.container'].browse(container_id)
        if not container:
            raise UserError('Container not found')
        plan = self.create({
            'plan_date': plan_date,
            'container_id': container_id,
            'state': 'draft',
        })
        container.write({'state': 'scheduled'})
        return plan.read(['id', 'plan_date', 'container_id', 'container_no', 'bl_no', 'state'])

    def delete_transport_plan(self, plan_id):
        plan = self.browse(plan_id)
        if not plan:
            return False
        container = plan.container_id
        plan.unlink()
        if container:
            other = self.search([('container_id', '=', container.id)], limit=1)
            if not other:
                container.write({'state': 'pending'})
        return True

    def update_transport_plan(self, plan_id, vals):
        plan = self.browse(plan_id)
        if not plan:
            raise UserError('Plan not found')
        plan.write(vals)
        return plan.read(['id', 'plan_date', 'container_id', 'container_no', 'bl_no', 'state'])

    def get_daily_plan_summary(self, start_date, end_date):
        plans = self.search_read([
            ('plan_date', '>=', start_date),
            ('plan_date', '<=', end_date),
        ], ['id', 'plan_date', 'container_id', 'container_no', 'bl_no', 'state'])
        result = {}
        for p in plans:
            ds = str(p['plan_date'])
            if ds not in result:
                result[ds] = {'count': 0, 'containers': []}
            result[ds]['count'] += 1
            result[ds]['containers'].append(p)
        return result
