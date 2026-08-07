# -*- coding: utf-8 -*-
import json

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class TransportOrder(models.Model):
    _name = 'tlmp.transport.order'

    ADDRESS_FIELDS = ('origin_street', 'origin_zip', 'origin_city', 'origin_state_id',
                      'origin_country_id', 'destination_street', 'destination_zip',
                      'destination_city', 'destination_state_id', 'destination_country_id')
    CARGO_SNAPSHOT_FIELDS = (
        'cargo_description', 'cargo_weight', 'cargo_volume',
        'pallet_count', 'package_count', 'cargo_line_ids', 'container_ids',
        'matrix_code', 'matrix_version', 'matrix_validation_result',
        'matrix_snapshot')

    def write(self, vals):
        if any(k in vals for k in self.ADDRESS_FIELDS):
            for rec in self:
                if rec.state in ('confirmed', 'done', 'cancelled'):
                    raise UserError(_('Address is readonly after order confirmation.'))
        if any(k in vals for k in self.CARGO_SNAPSHOT_FIELDS):
            for rec in self:
                if rec.snapshot_status in ('confirmed', 'locked'):
                    raise UserError(_('Cargo snapshot is frozen after order confirmation.'))
        if 'vehicle_requirement_snapshot' in vals:
            for rec in self:
                if rec.state in ('confirmed', 'done', 'cancelled'):
                    raise UserError(_('Vehicle requirement snapshot is frozen after order confirmation.'))
        return super().write(vals)
    _description = 'Transport Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string='Order No.', required=True, copy=False,
                       default=lambda self: _('New'))
    transport_type_id = fields.Many2one('tlmp.transport.type',
        string='Transport Type', required=True)
    scene_id = fields.Many2one('tlmp.transport.scene', string='Transport Scene',
        readonly=True, copy=False,
        help='Immutable snapshot — set at creation from request.scene_id, cannot change later.')
    fleet_operation_mode = fields.Selection([
        ('own_fleet', 'Own Fleet'),
        ('contracted', 'Contracted'),
        ('subcontracted', 'Subcontracted'),
    ], string='Fleet Mode', required=True, default='subcontracted')
    request_id = fields.Many2one('tlmp.transport.request', string='Request')
    quote_id = fields.Many2one('tlmp.transport.quote', string='Quote')
    inquiry_id = fields.Many2one('tlmp.transport.inquiry', string='Inquiry')
    pickup_plan_id = fields.Many2one(
        'pickup.plan', string='Pickup Plan',
        readonly=True, copy=False, index=True,
        help='Source document for plan-driven flow.')
    source_type = fields.Selection([
        ('plan_driven', 'Plan-Driven'),
        ('commercial', 'Commercial'),
    ], string='Source Type', compute='_compute_source_type', store=True)

    @api.depends('pickup_plan_id', 'quote_id', 'request_id')
    def _compute_source_type(self):
        for r in self:
            if r.pickup_plan_id:
                r.source_type = 'plan_driven'
            elif r.quote_id:
                r.source_type = 'commercial'
            elif r.request_id and r.request_id.request_type:
                r.source_type = r.request_id.request_type
            else:
                r.source_type = False

    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    carrier_id = fields.Many2one('res.partner', string='Carrier', required=True)
    carrier_contact = fields.Char(string='Carrier Contact')
    carrier_phone = fields.Char(string='Carrier Phone')
    pickup_location_id = fields.Many2one('res.partner', string='Pickup Location')
    delivery_location_id = fields.Many2one('res.partner', string='Delivery Location')
    place_of_departure = fields.Char(string='Place of Departure')
    place_of_destination = fields.Char(string='Place of Destination')
    # Sprint44: address snapshot from request
    origin_street = fields.Char(string='Origin Street')
    origin_zip = fields.Char(string='Origin Zip')
    origin_city = fields.Char(string='Origin City')
    origin_state_id = fields.Many2one('res.country.state', string='Origin State')
    origin_country_id = fields.Many2one('res.country', string='Origin Country')
    destination_street = fields.Char(string='Destination Street')
    destination_zip = fields.Char(string='Destination Zip')
    destination_city = fields.Char(string='Destination City')
    destination_state_id = fields.Many2one('res.country.state', string='Destination State')
    destination_country_id = fields.Many2one('res.country', string='Destination Country')
    transit_places = fields.Text(string='Transit Places')
    planned_pickup_date = fields.Datetime(string='Planned Pickup')
    planned_delivery_date = fields.Datetime(string='Planned Delivery')
    actual_pickup_date = fields.Datetime(string='Actual Pickup')
    actual_delivery_date = fields.Datetime(string='Actual Delivery')
    delivery_delay_hours = fields.Float(
        string='Delivery Delay (hours)',
        compute='_compute_delivery_delay', store=True,
        help='Actual delivery minus planned delivery in hours. Negative=early, Positive=late.')
    driver_name = fields.Char(string='Driver')
    driver_phone = fields.Char(string='Driver Phone')
    vehicle_plate = fields.Char(string='Vehicle Plate')
    cargo_description = fields.Text(string='Cargo')
    cargo_weight = fields.Float(string='Weight (kg)')
    cargo_volume = fields.Float(string='Volume (m3)')
    pallet_count = fields.Integer(string='Pallets')
    cargo_line_ids = fields.One2many('tlmp.transport.cargo.line', 'order_id', string='Cargo Lines')
    package_count = fields.Integer(string='Packages')
    cargo_snapshot_version = fields.Integer(
        string='Cargo Snapshot Version', default=1, readonly=True, copy=False)
    snapshot_status = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('locked', 'Locked'),
        ('cancelled', 'Cancelled'),
    ], string='Cargo Snapshot Status', default='draft', copy=False)
    matrix_code = fields.Char(string='Matrix Code', readonly=True)
    matrix_version = fields.Char(
        string='Matrix Version', default='V1.0', readonly=True)
    matrix_validation_result = fields.Selection([
        ('pass', 'PASS'),
        ('warning', 'WARNING'),
        ('block', 'BLOCK'),
    ], string='Matrix Result', readonly=True)
    matrix_snapshot = fields.Text(string='Matrix Snapshot', readonly=True)
    vehicle_requirement_snapshot = fields.Text(
        string='Vehicle Requirement Snapshot', readonly=True, copy=False,
        help='JSON snapshot of vehicle requirement at order creation. Frozen after confirm.')
    vehicle_allocation_snapshot = fields.Text(
        string='Vehicle Allocation Snapshot', copy=False,
        help='Sprint50: actual vehicle/driver allocation frozen at ORDER_ALLOCATED.')
    container_ids = fields.One2many('tlmp.transport.container', 'order_id', string='Containers')
    container_no_set = fields.Char(string='Container No. Set')
    swap_container = fields.Boolean(string='Swap Container')
    original_container_no = fields.Char(string='Original Container No.')
    new_container_no = fields.Char(string='New Container No.')
    surcharge_ids = fields.One2many('tlmp.surcharge', 'order_id', string='Surcharges')
    transport_event_ids = fields.One2many('tlmp.transport.event', 'order_id', string='Transport Events')
    exception_ids = fields.One2many('tlmp.transport.exception', 'order_id', string='Exceptions')
    extra_charge_ids = fields.One2many('tlmp.transport.extra.charge', 'order_id', string='Extra Charges')
    # Sprint19: computed attachment aggregates for categorized display
    cmr_attachment_ids = fields.Many2many(
        'ir.attachment', string='CMR Attachments',
        compute='_compute_category_attachments')
    event_attachment_ids = fields.Many2many(
        'ir.attachment', string='Event Attachments',
        compute='_compute_category_attachments')
    exception_attachment_ids = fields.Many2many(
        'ir.attachment', string='Exception Attachments',
        compute='_compute_category_attachments')
    charge_attachment_ids = fields.Many2many(
        'ir.attachment', string='Charge Attachments',
        compute='_compute_category_attachments')

    @api.depends('cmr_ids', 'transport_event_ids', 'exception_ids', 'extra_charge_ids')
    def _compute_category_attachments(self):
        Attachment = self.env['ir.attachment']
        for r in self:
            r.cmr_attachment_ids = Attachment
            r.event_attachment_ids = Attachment
            r.exception_attachment_ids = Attachment
            r.charge_attachment_ids = Attachment
            # CMR: gather from cmr record attachments
            for cmr in r.cmr_ids:
                r.cmr_attachment_ids |= cmr.attachment_ids
            # Events: gather from event attachments
            for evt in r.transport_event_ids:
                r.event_attachment_ids |= evt.attachment_ids
            # Exceptions: gather from exception attachments
            for exc in r.exception_ids:
                r.exception_attachment_ids |= exc.attachment_ids
            # Charges: gather from charge attachments
            for chg in r.extra_charge_ids:
                r.charge_attachment_ids |= chg.attachment_ids

    @api.depends('planned_delivery_date', 'actual_delivery_date')
    def _compute_delivery_delay(self):
        for r in self:
            if r.actual_delivery_date and r.planned_delivery_date:
                delta = r.actual_delivery_date - r.planned_delivery_date
                r.delivery_delay_hours = delta.total_seconds() / 3600.0
            else:
                r.delivery_delay_hours = 0.0

    total_base_fee = fields.Monetary(string='Base Fee')
    total_surcharge = fields.Monetary(string='Total Surcharge', compute='_compute_surcharge_total')
    total_carrier_cost = fields.Monetary(string='Carrier Cost')
    total_customer_charge = fields.Monetary(string='Customer Charge')
    source_amount_carrier = fields.Monetary(string='Source Amt (Carrier)', readonly=True)
    source_amount_customer = fields.Monetary(string='Source Amt (Customer)', readonly=True)
    price_source = fields.Selection([
        ('quote', 'From Quote'),
        ('inquiry', 'From Inquiry'),
        ('pricing_rule', 'Pricing Rule'),
        ('manual', 'Manual'),
        ('carrier_api', 'Carrier API'),
    ], string='Price Source', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    customer_bill_id = fields.Many2one('tlmp.customer.bill', string='Customer Bill', readonly=True)
    carrier_settlement_id = fields.Many2one('tlmp.carrier.settlement', string='Carrier Settlement',
                                            readonly=True)
    allocation_ids = fields.One2many(
        'tlmp.carrier.settlement.allocation', 'transport_order_id',
        string='Allocations')
    allocated_carrier_cost = fields.Monetary(
        string='Allocated Carrier Cost',
        currency_field='currency_id',
        compute='_compute_allocated_carrier_cost', store=False)
    billing_document_ids = fields.One2many(
        'tlmp.carrier.billing.line', 'transport_order_id',
        string='Billing Lines')
    cmr_ids = fields.One2many('tlmp.cmr', 'order_id', string='CMR Documents')
    pod_id = fields.Many2one('tlmp.pod', string='POD', readonly=True)
    trip_id = fields.Many2one('container.transport.plan', string='Trip Plan', index=True)
    settlement_locked = fields.Boolean(string='Settlement Locked', default=False)
    tracking_state = fields.Selection([
        ('draft', 'Draft'),
        ('pending_pickup', 'Pending Pickup'),
        ('in_transit', 'In Transit'),
        ('pending_signoff', 'Pending Sign-off'),
        ('completed', 'Completed'),
        ('exception_hold', 'Exception Hold'),
    ], string='Tracking Status', default='draft',
       help='6-state tracking status')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('assigned', 'Assigned'),
        ('allocated', 'Allocated'),
        ('in_transit', 'In Transit'),
        ('exception', 'Exception'),
        ('delivered', 'Delivered'),
        ('signed', 'Signed'),
        ('billed', 'Billed'),
        ('settlement_pending', 'Settlement Pending'),
        ('settled', 'Settled'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    exception_type = fields.Selection([
        ('delay', 'Delay'),
        ('damage', 'Damage'),
        ('customer_refuse', 'Customer Refuse'),
        ('document_issue', 'Document Issue'),
        ('customs_hold', 'Customs Hold'),
        ('vehicle_failure', 'Vehicle Failure'),
    ], string='Exception Type')
    exception_recovery = fields.Selection([
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ], string='Recovery Target')
    delivered_qty = fields.Float(string='Delivered Qty')
    has_dangerous_goods = fields.Boolean(string='DG', default=False)
    adr_un_number = fields.Char(string='UN No.')
    adr_class = fields.Char(string='ADR Class')
    adr_packing_group = fields.Selection([('I', 'I'), ('II', 'II'), ('III', 'III'),
                                          ('none', 'N/A')], string='PG')
    adr_tunnel_code = fields.Selection([
        ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'),
        ('B/D', 'B/D'), ('C/D', 'C/D'), ('D/E', 'D/E'),
    ], string='Tunnel Code')
    customs_transit_ref = fields.Char(string='T1 MRN')
    customs_declaration_ref = fields.Char(string="Customs Decl. Ref.")
    mrn_code = fields.Char(string='MRN Code')
    t1_ref = fields.Char(string='T1 Reference')
    dg_file_ref = fields.Char(string='DG File Reference')
    adr_quantity = fields.Float(string='ADR Quantity')
    adr_weight = fields.Float(string='ADR Weight (kg)')
    t1_deadline = fields.Datetime(string='T1 Transit Deadline',
                                   help='Customs transit deadline for T1 documents')
    dgd_ids = fields.One2many('tlmp.transport.dgd', 'order_id', string='DGD Documents')
    shipment_label_ids = fields.One2many('tlmp.transport.shipment.label', 'order_id',
                                         string='Shipment Labels')
    t1_state = fields.Selection([
        ('none', 'None'),
        ('declared', 'Declared'),
        ('in_transit', 'In Transit'),
        ('arrived', 'Arrived'),
        ('closed', 'Closed'),
    ], string='T1 State', default='none')
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company)

    @api.depends('fee_line_ids.amount', 'fee_line_ids.party_type')
    def _compute_estimated_cost(self):
        for r in self:
            r.estimated_carrier_cost = sum(
                r.fee_line_ids.filtered(lambda l: l.party_type == 'carrier_cost'
                ).mapped('amount'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tlmp.order.seq') or _('New')
            # Safety defaults for required fields
            if not vals.get('partner_id'):
                partner = self.env['res.partner'].create({'name': 'System Partner'})
                vals['partner_id'] = partner.id
            if not vals.get('carrier_id'):
                carrier = self.env['res.partner'].create({'name': 'System Carrier'})
                vals['carrier_id'] = carrier.id
            if not vals.get('transport_type_id'):
                vals['transport_type_id'] = self.env['tlmp.transport.type']._get_by_code('port_to_warehouse').id
            if not vals.get('fleet_operation_mode'):
                vals['fleet_operation_mode'] = 'subcontracted'
        records = super().create(vals_list)
        for rec in records:
            self.env['tlmp.transport.reference'].create_for_order(rec)
        return records

    @api.depends('surcharge_ids.amount')
    def _compute_surcharge_total(self):
        for r in self:
            r.total_surcharge = sum(r.surcharge_ids.mapped('amount'))

    # -----------------------------------------------------------
    # Upstream status sync
    # -----------------------------------------------------------
    def _sync_upstream_status(self):
        """Sync order status back to upstream documents."""
        for r in self:
            # Plan-driven: update pickup.plan state
            if r.pickup_plan_id:
                r.pickup_plan_id.scheduled_date = r.planned_pickup_date.date() if r.planned_pickup_date else r.pickup_plan_id.scheduled_date
            # Commercial: ensure quote is marked accepted
            if r.quote_id and r.quote_id.state != 'accepted':
                r.quote_id.sudo().write({'state': 'accepted'})

    # -----------------------------------------------------------
    # Dual-source creation assistant
    # -----------------------------------------------------------
    @api.model
    def create_from_pickup_plan(self, pickup_plan):
        """Create transport.order from a pickup.plan (plan-driven flow)."""
        type_map = {'warehouse': 'port_to_warehouse', 'warehouse_transfer': 'warehouse_transfer',
                    'customer': 'to_customer', 'self_pickup': 'to_customer'}
        tr_type = type_map.get(pickup_plan.destination_type, 'port_to_warehouse')
        val = {
            'scene_id': pickup_plan.transport_request_id.scene_id.id if pickup_plan.transport_request_id and pickup_plan.transport_request_id.scene_id else False,
            'transport_type_id': self.env['tlmp.transport.type']._get_by_code(tr_type).id,
            'fleet_operation_mode': 'subcontracted',
            'pickup_plan_id': pickup_plan.id,
            'request_id': pickup_plan.transport_request_id.id if pickup_plan.transport_request_id else False,
            'partner_id': pickup_plan.partner_id.id or pickup_plan.carrier_id.id or False,
            'carrier_id': pickup_plan.carrier_id.id if pickup_plan.carrier_id else False,
            'cargo_description': pickup_plan.cargo_description or '',
            'cargo_weight': pickup_plan.cargo_weight,
            'cargo_volume': pickup_plan.cargo_volume,
            'pallet_count': pickup_plan.pallet_count,
            'package_count': pickup_plan.package_count,
            'planned_pickup_date': pickup_plan.planned_pickup_date or pickup_plan.scheduled_date,
            'driver_name': pickup_plan.driver_name,
            'driver_phone': pickup_plan.driver_phone,
            'vehicle_plate': pickup_plan.vehicle_plate,
            'notes': pickup_plan.notes,
        }
        if pickup_plan.destination_type == 'warehouse_transfer':
            val['pickup_location_id'] = pickup_plan.source_warehouse_id.partner_id.id if pickup_plan.source_warehouse_id else False
            val['delivery_location_id'] = pickup_plan.warehouse_id.partner_id.id if pickup_plan.warehouse_id else False
        else:
            val['delivery_location_id'] = pickup_plan.warehouse_id.partner_id.id if pickup_plan.warehouse_id else False
            if pickup_plan.terminal_id:
                val['pickup_location_id'] = pickup_plan.terminal_id.id
        order = self.create(val)
        # Copy container lines
        for cl in pickup_plan.container_line_ids:
            self.env['tlmp.transport.container'].create({
                'order_id': order.id, 'name': cl.container_number,
                'container_type': cl.container_type, 'seal_number': cl.seal_number,
                'cargo_weight_kg': cl.weight,
                'container_master_id': cl.container_master_id.id if cl.container_master_id else False,
            })
        return order

    # ---- State Transitions ----
    def action_confirm(self):
        engine = self.env['tlmp.workflow.engine']
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft orders can be confirmed.'))
            engine.transition(
                rec, 'confirmed', 'ORDER_CONFIRMED',
                extra_vals={'snapshot_status': 'confirmed'})
        self._sync_upstream_status()
        return True

    def action_assign(self):
        engine = self.env['tlmp.workflow.engine']
        for rec in self:
            engine.transition(rec, 'assigned', 'ORDER_ASSIGNED')
        return True

    def action_allocate(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Only confirmed orders can be allocated.'))
        req = self.request_id
        plan = self.pickup_plan_id
        abstract = plan.transport_plan_id if plan else (
            self.trip_id.transport_plan_id if self.trip_id else False)
        if req and req.vehicle_requirement_mode_snapshot == 'exempted':
            self.env['tlmp.workflow.engine'].transition(
                self, 'allocated', 'ORDER_ALLOCATED')
            return True
        snapshot = {}
        if req and req.vehicle_requirement_mode_snapshot == 'required':
            req_snapshot = json.loads(req.vehicle_requirement_snapshot or '{}')
            if not req.vehicle_requirement_snapshot or \
                    req_snapshot.get('vehicle_requirement_validation_result') \
                    == 'block':
                raise UserError(_(
                    'Vehicle requirement snapshot is missing or invalid.'))
            if not abstract or not abstract.allocation_candidate_valid \
                    or not abstract.allocation_candidate:
                raise UserError(_(
                    'Allocation candidate is missing; '
                    'plan.reserve must be completed first.'))
            candidate = json.loads(abstract.allocation_candidate)
            if self.carrier_id and candidate.get('reserved_carrier_id') \
                    and candidate['reserved_carrier_id'] != self.carrier_id.id:
                raise UserError(_(
                    'Assigned carrier changed since plan reservation.'))
            if self.vehicle_plate and candidate.get('reserved_vehicle_plate') \
                    and candidate['reserved_vehicle_plate'] != self.vehicle_plate:
                raise UserError(_(
                    'Assigned vehicle changed since plan reservation.'))
            if self.driver_name and candidate.get('reserved_driver') \
                    and candidate['reserved_driver'] != self.driver_name:
                raise UserError(_(
                    'Assigned driver changed since plan reservation.'))
            snapshot = {
                'valid': True,
                'vehicle_requirement_mode': req.vehicle_requirement_mode_snapshot,
                'vehicle_body_type': req.vehicle_body_type,
                'vehicle_capacity_requirement':
                    req.vehicle_capacity_requirement,
                'is_dangerous_goods': req.is_dangerous_goods,
                'assigned_carrier_id': (
                    self.carrier_id.id if self.carrier_id else False),
                'assigned_vehicle_plate': self.vehicle_plate or False,
                'assigned_driver': self.driver_name or False,
                'assignment_context': candidate.get('assignment_context'),
            }
        self.env['tlmp.workflow.engine'].transition(
            self, 'allocated', 'ORDER_ALLOCATED',
            extra_vals={'vehicle_allocation_snapshot': json.dumps(
                snapshot, ensure_ascii=False)},
            payload=json.dumps(snapshot, ensure_ascii=False))
        return True

    def transition_to_allocated(self):
        """Canonical Sprint50-A allocation action; ORDER_ALLOCATED records fact."""
        return self.action_allocate()

    def action_raise_exception(self, exception_type='delay',
                               recovery='in_transit'):
        self.ensure_one()
        if self.state not in ('allocated', 'in_transit'):
            raise UserError(
                _('Only allocated/in_transit orders can enter exception.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'exception', 'ORDER_EXCEPTION',
            extra_vals={
                'exception_type': exception_type,
                'exception_recovery': recovery,
            })
        return True

    def action_recover_exception(self):
        self.ensure_one()
        if self.state != 'exception' or not self.exception_recovery:
            raise UserError(
                _('Recovery target is required to leave exception state.'))
        self.env['tlmp.workflow.engine'].transition(
            self, self.exception_recovery, 'ORDER_EXCEPTION_RECOVERED')
        return True

    def action_enter_settlement(self):
        self.ensure_one()
        if self.state not in ('delivered', 'signed'):
            raise UserError(_('Only delivered orders can enter settlement.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'settlement_pending', 'ORDER_SETTLEMENT_PENDING')
        return True

    def action_start_transit(self):
        self.env['tlmp.workflow.engine'].transition(
            self, 'in_transit', 'ORDER_IN_TRANSIT',
            extra_vals={'actual_pickup_date': fields.Datetime.now()})
        return True

    def action_deliver(self):
        self.env['tlmp.workflow.engine'].transition(
            self, 'delivered', 'ORDER_DELIVERED',
            extra_vals={'actual_delivery_date': fields.Datetime.now()})
        return True

    def action_confirm_pod(self):
        self.env['tlmp.workflow.engine'].transition(
            self, 'signed', 'ORDER_POD_CONFIRMED')
        # Update container history: record return date
        HistoryLine = self.env['container.master.history.line']
        for container in self.container_ids:
            if not container.container_master_id:
                continue
            # Find the most recent inbound history line for this master
            hist = HistoryLine.search([
                ('master_id', '=', container.container_master_id.id),
                ('return_date', '=', False),
            ], limit=1, order='id desc')
            if hist:
                hist.write({
                    'return_date': fields.Date.today(),
                    'location_end': self.delivery_location_id.name if self.delivery_location_id else False,
                })
        return True

    def action_bill(self):
        lock = self._check_settle_lock()
        if lock['locked']:
            raise UserError(_('Cannot bill: %s') % lock['reason'])
        self.env['tlmp.workflow.engine'].transition(
            self, 'billed', 'ORDER_BILLED')
        return True

    def action_settle(self):
        lock = self._check_settle_lock()
        if lock['locked']:
            raise UserError(_('Cannot settle: %s') % lock['reason'])
        self.env['tlmp.workflow.engine'].transition(
            self, 'settled', 'ORDER_SETTLED')
        return True

    def action_close(self):
        self.ensure_one()
        if self.pod_id and self.pod_id.state not in (False, "confirmed"):
            raise UserError(_('Cannot close order: POD must be confirmed first.'))
        # # Sprint16: validate all exceptions CLOSED
        open_ex = self.exception_ids.filtered(lambda e: e.exception_state != 'closed')
        if open_ex:
            raise UserError(_(
                'Cannot close order: %d exception(s) are not CLOSED. '
                'All exceptions must be resolved and closed before archiving.'
            ) % len(open_ex))
        self.env['tlmp.workflow.engine'].transition(
            self, 'closed', 'ORDER_CLOSED',
            extra_vals={'tracking_state': 'completed'})
        return True

    def action_cancel(self, reason=None):
        engine = self.env['tlmp.workflow.engine']
        for rec in self:
            engine.transition(
                rec, 'cancelled', 'ORDER_CANCELLED',
                payload=reason or False)
        return True

    def action_reject(self, reason=None):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Only confirmed orders can be rejected to draft.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'draft', 'ORDER_REOPENED')
        return True

    def action_archive(self):
        self.ensure_one()
        open_ex = self.exception_ids.filtered(lambda e: e.exception_state != 'closed')
        if open_ex:
            raise UserError(_(
                'Cannot archive: %d exception(s) are not CLOSED.'
            ) % len(open_ex))
        self.write({'tracking_state': 'completed', 'state': 'closed'})

    def action_void(self, reason=None):
        self.ensure_one()
        self.env['tlmp.workflow.engine'].transition(
            self, 'cancelled', 'ORDER_CANCELLED',
            payload=reason or False)
        return True

    # ---- Settlement Lock ----
    def _check_settle_lock(self):
        self.ensure_one()
        # Removed POD/CMR mandatory check per Sprint11 decision
        if self.pod_id and self.pod_id.state in ('disputed',):
            return {'locked': True, 'reason': 'POD has unresolved dispute'}
        if self.pod_id and self.pod_id.goods_condition in ('damaged', 'short', 'rejected'):
            return {'locked': True, 'reason': 'POD has damage/short/rejected issue'}
        if self.settlement_locked:
            return {'locked': True, 'reason': 'Order is locked (damage/claim pending)'}
        return {'locked': False}

    def compute_pricing(self):
        self.ensure_one()
        # Priority 1: Inherit from accepted quote
        if self.quote_id and self.quote_id.state == 'accepted':
            self.total_customer_charge = self.quote_id.total_amount
            self.source_amount_customer = self.quote_id.total_amount
            if self.inquiry_id:
                self.total_carrier_cost = self.inquiry_id.total_amount
                self.source_amount_carrier = self.inquiry_id.total_amount
            self.price_source = 'quote'
            return True
        # Priority 2: Inherit from inquiry
        if self.inquiry_id and self.inquiry_id.state == 'accepted':
            self.total_carrier_cost = self.inquiry_id.total_amount
            self.source_amount_carrier = self.inquiry_id.total_amount
            margin = float(self.env['ir.config_parameter'].sudo().get_param(
                'tlmp.service_margin_rate', default=0.15))
            self.total_customer_charge = self.total_carrier_cost * (1 + margin)
            self.source_amount_customer = self.total_customer_charge
            self.price_source = 'inquiry'
            return True
        # Priority 3: Use pricing rules
        rules = self.env['tlmp.pricing.rule'].search([
            ('active', '=', True),
            ('transport_type_id', '=', self.transport_type_id.id),
            ('carrier_type', '=', self.fleet_operation_mode),
        ], order='priority asc', limit=1)
        if rules:
            rule = rules[0]
            self.price_source = 'pricing_rule'
            # Apply the first matching tier
            tier = rule.line_ids.filtered(
                lambda l: (not l.min_value or self.cargo_weight >= l.min_value)
                and (not l.max_value or self.cargo_weight <= l.max_value)
            )
            if tier:
                self.total_carrier_cost = tier[0].base_fee + (tier[0].unit_price * self.cargo_weight)
                self.source_amount_carrier = self.total_carrier_cost
                margin = float(self.env['ir.config_parameter'].sudo().get_param(
                    'tlmp.service_margin_rate', default=0.15))
                self.total_customer_charge = self.total_carrier_cost * (1 + margin)
                self.source_amount_customer = self.total_customer_charge
        else:
            self.price_source = 'manual'
        return True

    @api.depends('allocation_ids.allocated_amount')
    def _compute_allocated_carrier_cost(self):
        for r in self:
            r.allocated_carrier_cost = sum(
                r.allocation_ids.mapped('allocated_amount'))

    def action_open_references(self):
        """Open references linked to this transport order."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'References',
            'res_model': 'tlmp.transport.reference',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', 'tlmp.transport.order'),
                       ('res_id', '=', self.id)],
            'context': {'default_res_model': 'tlmp.transport.order',
                        'default_res_id': self.id,
                        'default_ref_type': 'shipment_no',
                        'default_ref_value': self.name},
        }
