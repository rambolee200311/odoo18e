# -*- coding: utf-8 -*-
import json

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

from ..business_matrix.rule_engine import BusinessMatrixEngine
from ..business_matrix.rule_definition import (
    SCENE_S_CODES, BUSINESS_DRIVER, CARGO_CATEGORY,
    CARRIER_TYPE, T1_ATTRIBUTE, DG_ATTRIBUTE)
from ..business_matrix.rules.vehicle_rules import check_vehicle_rules


class TransportRequest(models.Model):
    _name = 'tlmp.transport.request'

    _name = 'tlmp.transport.request'
    _description = 'Transport Request (Unified Entry Point)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'
    _rec_name = 'name'
    _VEHICLE_FROZEN_FIELDS = (
        'vehicle_requirement_mode_snapshot',
        'vehicle_requirement_snapshot',
        'vehicle_requirement_snapshot_status',
        'vehicle_body_type',
        'vehicle_capacity_requirement',
        'is_dangerous_goods',
        'dg_adr_class',
        'dg_un_code',
    )
        # ---- Identity ----
    name = fields.Char(string='Request No.', required=True, copy=False,
                      default=lambda self: _('New'))
    scene_code = fields.Char(related='scene_id.code', string='Scene Code', store=True, readonly=True)
    scene_id = fields.Many2one('tlmp.transport.scene', string='Transport Scene',
                               help='Sprint40: scene becomes the primary business dimension. Replaces old request_type+destination_type two-dimensional flow model.')

    # ---- Flow Control (determines downstream path) ----
    request_type = fields.Selection([
       ('plan_driven', 'Plan-Driven'),
       ('commercial', 'Commercial'),
    ], string='Request Type', required=True, default='plan_driven',
       help='Plan-Driven: Schedule + pickup.plan + order. Commercial: Inquiry + Quote + order.')

    destination_type = fields.Selection([
       ('warehouse', 'Terminal / Depot to Our Warehouse'),
       ('warehouse_transfer', 'Our Warehouse Transfer'),
       ('customer', 'Terminal / Depot to Customer'),
       ('self_pickup', 'Customer Self-Pickup'),
    ], string='Destination', required=True, default='warehouse',
       help='Aligns with IFFM import.pickup.requirement.pickup_scene.')

    source_type = fields.Selection([
       ('iff', 'From IFF (wd_iffm)'),
       ('manual', 'Manual Entry'),
    ], string='Source', default='manual', required=True)

    transport_type_id = fields.Many2one('tlmp.transport.type',
       string='Transport Type', required=True,
       default=lambda self: self.env['tlmp.transport.type']._get_by_code('port_to_warehouse').id)

    # ---- Cargo type control ----
    cargo_type = fields.Selection([
       ('container', 'Container'),
       ('pallet', 'Pallet'),
       ('piece', 'Piece / Bulk'),
    ], string='Cargo Type', default='container', required=True)
    business_driver = fields.Selection([
       ('plan_driven', 'B1 Plan-Driven'),
       ('commercial', 'B2 Commercial'),
    ], string='Business Driver', default='plan_driven', required=True,
       help='Business matrix dimension B.')
    cargo_category = fields.Selection([
       ('container', 'C1 Container'),
       ('pallet', 'C2 Pallet'),
       ('piece', 'C3 Piece'),
    ], string='Cargo Category', compute='_compute_cargo_category', store=True,
       help='Business matrix dimension C; root determines the Cargo Category.')
    carrier_type = fields.Selection([
       ('own_fleet', 'D1 Own Fleet'),
       ('truck', 'D2 Third-Party Truck'),
       ('courier', 'D3 Courier'),
    ], string='Carrier Type', default='truck', required=True,
       help='Business matrix dimension D.')
    t1_attribute = fields.Selection([
       ('t1', 'E1 T1'),
       ('normal', 'E2 Normal'),
    ], string='T1 Attribute', default='normal', required=True,
       help='Business matrix dimension E.')
    dg_attribute = fields.Selection([
       ('dg', 'F1 Dangerous'),
       ('normal', 'F2 Normal'),
    ], string='DG Attribute', default='normal', required=True,
       help='Business matrix dimension F.')
    matrix_code = fields.Char(
       string='Matrix Code', compute='_compute_matrix_code', store=True,
       help='Six-dimension combination code, e.g. S1-B1-C1-D2-E2-F2.')
    matrix_version = fields.Char(
       string='Matrix Version', default='V1.0', readonly=True, copy=False)
    matrix_snapshot_status = fields.Selection([
       ('draft', 'Draft'),
       ('frozen', 'Frozen'),
    ], string='Matrix Snapshot Status', default='draft', readonly=True, copy=False)
    matrix_validation_result = fields.Selection([
       ('pass', 'PASS'),
       ('warning', 'WARNING'),
       ('block', 'BLOCK'),
    ], string='Matrix Validation', compute='_compute_matrix_validation', store=True)
    matrix_validation_violations = fields.Text(
       string='Matrix Violations', compute='_compute_matrix_validation', store=True)

    # ---- Cargo fields (pallet goes to pickup.plan, container mgmt at pickup.plan level) ----
    cargo_line_ids = fields.One2many("tlmp.transport.cargo.line", "request_id", string="Cargo Lines")
    pallet_count = fields.Integer(string="Pallets")
    package_count = fields.Integer(string='Packages')
    cargo_weight = fields.Float(string='Weight (kg)', digits='Stock Weight')
    cargo_volume = fields.Float(string='Volume (m3)', digits='Volume')
    cargo_description = fields.Text(string='Cargo Description')

    # ---- Partner ----
    partner_id = fields.Many2one('res.partner', string='Customer',
                                domain=[('is_company', '=', True)],
                                help='Cargo owner / entrusting customer. Optional when the destination is entered manually as a free address.')
    customer_ref = fields.Char(string='Customer Reference')
    contact_person = fields.Char(string='Contact Person')
    contact_phone = fields.Char(string='Contact Phone')
    contact_email = fields.Char(string='Contact Email')

    # ---- Destination / Scene fields ----
    terminal_id = fields.Many2one('res.partner', string='Origin Terminal / Port',
                                 domain=[('is_company', '=', True)])
    warehouse_id = fields.Many2one('stock.warehouse', string='Destination Warehouse')
    source_warehouse_id = fields.Many2one('stock.warehouse', string='Source Warehouse')
    delivery_address = fields.Text(string='Delivery Address')
    delivery_contact = fields.Char(string='Delivery Contact')
    delivery_phone = fields.Char(string='Delivery Phone')

    # Sprint44: structured origin address fields
    origin_street = fields.Char(string='Origin Street')
    origin_zip = fields.Char(string='Origin Zip')
    origin_city = fields.Char(string='Origin City')
    origin_state_id = fields.Many2one('res.country.state', string='Origin State')
    origin_country_id = fields.Many2one('res.country', string='Origin Country')
    # Sprint44: structured destination address fields
    destination_street = fields.Char(string='Destination Street')
    destination_zip = fields.Char(string='Destination Zip')
    destination_city = fields.Char(string='Destination City')
    destination_state_id = fields.Many2one('res.country.state', string='Destination State')
    destination_country_id = fields.Many2one('res.country', string='Destination Country')
    pickup_location_id = fields.Many2one('res.partner', string='Pickup Location')
    delivery_location_id = fields.Many2one('res.partner', string='Delivery Location')

    # ---- Scheduling fields ----
    carrier_id = fields.Many2one('res.partner', string='Trucking Company',
                                domain=[('is_carrier', '=', True)])
    planned_pickup_date = fields.Datetime(string='Planned Pickup')
    driver_name = fields.Char(string='Driver Name')
    driver_phone = fields.Char(string='Driver Phone')
    vehicle_plate = fields.Char(string='Vehicle Plate')

    # ---- Vehicle Requirement fields (Sprint49-B) ----
    vehicle_requirement_mode = fields.Selection([
        ('required', 'Required'),
        ('exempted', 'Exempted'),
    ], string='Vehicle Requirement Mode',
        compute='_compute_vehicle_requirement_mode', store=True,
        help='Readonly compute: derived from carrier_type via carrier_type_vehicle_policy. '
             'Required → full vehicle validation. Exempted → skip all vehicle checks.')
    vehicle_requirement_mode_snapshot = fields.Selection([
        ('required', 'Required'),
        ('exempted', 'Exempted'),
    ], string='Vehicle Req. Mode Snapshot', readonly=True, copy=False,
        help='Frozen on confirm. Protected from subsequent policy changes.')
    vehicle_requirement_validation_result = fields.Selection([
        ('pass', 'PASS'),
        ('warning', 'WARNING'),
        ('block', 'BLOCK'),
    ], string='Vehicle Requirement Result', default='pass', copy=False)
    vehicle_requirement_validation_violations = fields.Text(
        string='Vehicle Requirement Violations', copy=False)
    vehicle_requirement_snapshot_status = fields.Selection([
        ('draft', 'Draft'),
        ('frozen', 'Frozen'),
    ], string='Vehicle Requirement Snapshot Status', default='draft', copy=False)
    vehicle_requirement_snapshot = fields.Text(
        string='Vehicle Requirement Snapshot', copy=False)
    vehicle_body_type = fields.Selection([
        ('no_requirement', 'No Requirement'),
        ('rear_only', 'Rear Only'),
        ('side_loading', 'Side Loading'),
        ('side_rear_both', 'Side & Rear'),
        ('top_loading', 'Top Loading'),
        ('tail_lift', 'Tail Lift'),
        ('open_flatbed', 'Open Flatbed'),
        ('reefer_refrigerated', 'Reefer'),
        ('tanker', 'Tanker'),
    ], string='Vehicle Body Type', default='no_requirement',
        help='Required loading/unloading form for the assigned vehicle.')
    vehicle_capacity_requirement = fields.Selection([
        ('no_limit', 'No Limit'),
        ('below_40t', '< 40t'),
        ('40t_44t', '40t-44t'),
        ('over_44t', '> 44t'),
    ], string='Vehicle Capacity Req.', default='no_limit',
        help='Minimum rated capacity constraint for assigned vehicle (tons).')
    is_dangerous_goods = fields.Selection([
        ('normal', 'Normal'),
        ('adr_dangerous', 'ADR Dangerous'),
    ], string='DG Vehicle Requirement', default='normal',
        compute='_compute_is_dangerous_goods',
        help='Whether an ADR-certified vehicle is required. '
             'Derived from cargo dangerous goods profile.')
    dg_adr_class = fields.Char(string='ADR Class',
        help='ADR class when is_dangerous_goods=adr_dangerous (e.g. 3, 8).')
    dg_un_code = fields.Char(string='UN Code',
        help='UN number when is_dangerous_goods=adr_dangerous (e.g. UN1203).')

    # ---- Dates ----
    requested_pickup_date = fields.Datetime(string='Requested Pickup')
    requested_delivery_date = fields.Datetime(string='Requested Delivery')

    # ---- Downstream document links ----
    pickup_plan_ids = fields.One2many('pickup.plan', 'transport_request_id',
                                      string='Pickup Plans', copy=False)
    inquiry_ids = fields.One2many('tlmp.transport.inquiry', 'request_id',
                                  string='Inquiries', copy=False)
    quote_ids = fields.One2many('tlmp.transport.quote', 'request_id',
                                string='Quotes', copy=False)
    order_ids = fields.One2many('tlmp.transport.order', 'request_id',
                                string='Orders', copy=False)
    has_accepted_quote = fields.Boolean(
        string='Has Accepted Quote', compute='_compute_has_accepted_quote', store=True,
        help='Whether the commercial flow already has an accepted quote.')

    @api.depends('quote_ids.state')
    def _compute_has_accepted_quote(self):
        for r in self:
            r.has_accepted_quote = any(q.state == 'accepted' for q in r.quote_ids)

    # ---- Sprint50: validation state + partial fulfillment ----
    validation_state = fields.Selection([
        ('pending', 'Pending'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
    ], string='Validation State', default='pending', tracking=True)
    fulfillment_status = fields.Selection([
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Fulfillment Status', default='pending')
    requested_qty = fields.Float(string='Requested Qty')
    planned_qty = fields.Float(string='Planned Qty')
    ordered_qty = fields.Float(
        string='Ordered Qty', compute='_compute_fulfillment_counts', store=True)
    delivered_qty = fields.Float(
        string='Delivered Qty', compute='_compute_fulfillment_counts', store=True)
    total_order_count = fields.Integer(
        string='Total Orders', compute='_compute_fulfillment_counts', store=True)
    settled_order_count = fields.Integer(
        string='Settled Orders', compute='_compute_fulfillment_counts', store=True)
    closed_order_count = fields.Integer(
        string='Closed Orders', compute='_compute_fulfillment_counts', store=True)

    @api.depends('order_ids.state', 'order_ids.delivered_qty',
                 'order_ids.cargo_weight')
    def _compute_fulfillment_counts(self):
        for r in self:
            orders = r.order_ids
            r.total_order_count = len(orders)
            r.settled_order_count = len(orders.filtered(
                lambda o: o.state in ('settled', 'closed')))
            r.closed_order_count = len(orders.filtered(
                lambda o: o.state in ('settled', 'closed', 'cancelled')))
            r.ordered_qty = sum(orders.mapped('cargo_weight')) if orders \
                else (r.requested_qty or 0.0)
            r.delivered_qty = sum(orders.mapped('delivered_qty')) if orders \
                else 0.0

    # ---- Misc ----
    special_requirements = fields.Text(string='Special Requirements')
    has_dangerous_goods = fields.Boolean(string='Dangerous Goods', default=False)
    customs_declaration_ref = fields.Char(string='Customs Decl. Ref.')
    wms_transfer_order_ref = fields.Char(string='WMS Transfer Ref.')

    # ---- Status ----
    state = fields.Selection([
       ('draft', 'Draft'),
       ('submitted', 'Submitted'),
       ('confirmed', 'Confirmed'),
       ('processing', 'Processing'),
       ('completed', 'Completed'),
       ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    # -----------------------------------------------------------
    # Sequence
    # -----------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('skip_vehicle_requirement_validation'):
            return super().create(vals_list)
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tlmp.request.seq') or _('New')
            if not vals.get('business_driver') and vals.get('request_type'):
                vals['business_driver'] = vals['request_type']
            if not vals.get('dg_attribute') and vals.get('has_dangerous_goods'):
                vals['dg_attribute'] = 'dg' if vals.get('has_dangerous_goods') else 'normal'
            self._prepare_vehicle_requirement_vals(vals)
            self._raise_if_matrix_block_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('skip_vehicle_requirement_validation'):
            return super().write(vals)
        if any(k in vals for k in self._VEHICLE_FROZEN_FIELDS):
            for r in self:
                if r.state == 'confirmed' or r.vehicle_requirement_snapshot_status == 'frozen':
                    raise UserError(
                        _('Vehicle requirement fields are frozen after request confirmation.'))
        for r in self:
            self._prepare_vehicle_requirement_vals(vals, record=r)
            self._raise_if_matrix_block_vals(vals, record=r)
        return super().write(vals)

    def _prepare_vehicle_requirement_vals(self, vals, record=None):
        context = self._vehicle_requirement_context(vals, record)
        violations = check_vehicle_rules(context)
        result = 'block' if any(v.get('result') == 'block' for v in violations) else 'warning' if violations else 'pass'
        vals['vehicle_requirement_validation_result'] = result
        vals['vehicle_requirement_validation_violations'] = json.dumps(violations, ensure_ascii=False)
        if not vals.get('vehicle_requirement_snapshot') and record and record.vehicle_requirement_snapshot_status == 'frozen':
            vals['vehicle_requirement_snapshot'] = record.vehicle_requirement_snapshot
        if not vals.get('vehicle_requirement_snapshot_status') and record and record.vehicle_requirement_snapshot_status == 'frozen':
            vals['vehicle_requirement_snapshot_status'] = 'frozen'

    def _vehicle_requirement_context(self, vals, record=None):
        request = record or self
        current_carrier_type = vals.get('carrier_type', request.carrier_type if request else False)
        current_mode = vals.get('vehicle_requirement_mode', request.vehicle_requirement_mode if request else False)
        current_body_type = vals.get('vehicle_body_type', request.vehicle_body_type if request else 'no_requirement')
        current_capacity = vals.get('vehicle_capacity_requirement', request.vehicle_capacity_requirement if request else 'no_limit')
        current_is_dg = vals.get('is_dangerous_goods')
        if not current_is_dg:
            if record:
                current_is_dg = record.is_dangerous_goods
            else:
                current_is_dg = ('adr_dangerous'
                                 if vals.get('dg_attribute') == 'dg'
                                 or vals.get('has_dangerous_goods') else 'normal')
        cargo_lines = record.cargo_line_ids if record else self.env['tlmp.transport.cargo.line']
        if record is None and vals.get('id'):
            record = self.browse(vals['id'])
        if record:
            cargo_lines = record.cargo_line_ids
        if not cargo_lines and vals.get('cargo_line_ids'):
            cargo_lines = self.env['tlmp.transport.cargo.line'].browse(
                [line[1] for line in vals.get('cargo_line_ids', []) if line[0] in (4, 5, 6)]
            )
        dangerous_lines = cargo_lines.filtered(lambda line: getattr(line, 'has_dangerous_goods', False))
        if record and record.has_dangerous_goods and not dangerous_lines:
            dangerous_lines = cargo_lines
        return {
            'vehicle_requirement_mode': current_mode or self._get_vehicle_policy_mode(current_carrier_type),
            'vehicle_body_type': current_body_type,
            'vehicle_capacity_requirement': current_capacity,
            'is_dangerous_goods': current_is_dg,
            'dg_adr_class': vals.get('dg_adr_class', record.dg_adr_class if record else False),
            'dg_un_code': vals.get('dg_un_code', record.dg_un_code if record else False),
            'carrier_type': current_carrier_type,
            'carrier_capabilities': set(
                self.env['res.partner'].browse(vals.get('carrier_id', record.carrier_id.id if record and record.carrier_id else False)).carrier_capability_ids.mapped('code')
            ) if vals.get('carrier_id', record.carrier_id.id if record and record.carrier_id else False) else set(),
            'has_dangerous_goods': bool(vals.get('has_dangerous_goods', record.has_dangerous_goods if record else False)),
            'assigned_vehicle_capacity': vals.get('assigned_vehicle_capacity'),
            'assigned_vehicle_body_type': vals.get('assigned_vehicle_body_type'),
            'assigned_vehicle_adr': vals.get('assigned_vehicle_adr'),
            'dangerous_goods_lines': dangerous_lines,
            'cargo_lines': cargo_lines,
        }

    def _get_vehicle_policy_rule(self, carrier_type):
        if not carrier_type:
            return self.env['tlmp.business.rule']
        return self.env['tlmp.business.rule'].sudo().search([
            ('active', '=', True),
            ('carrier_type', '=', carrier_type),
            ('vehicle_policy_mode', '!=', False),
        ], order='priority', limit=1)

    def _get_vehicle_policy_mode(self, carrier_type):
        policy_rule = self._get_vehicle_policy_rule(carrier_type)
        return policy_rule.vehicle_policy_mode if policy_rule else 'required'

    def _raise_if_matrix_block_vals(self, vals, record=None):
        ctx = self._matrix_vals_context(vals, record)
        res = BusinessMatrixEngine.validate(self.env, ctx)
        if res['result'] == 'block':
            msgs = '; '.join(v.get('message', '') for v in res['violations'])
            raise UserError(_('Business Matrix BLOCK: %s') % msgs)

    def _matrix_vals_context(self, vals, record=None):
        scene_id = vals.get('scene_id', record.scene_id.id if record else False)
        carrier_id = vals.get('carrier_id', record.carrier_id.id if record else False)
        capabilities = set()
        if carrier_id:
            capabilities = set(
                self.env['res.partner'].browse(carrier_id)
                .carrier_capability_ids.mapped('code'))
        categories = set()
        if record:
            categories = set(record.cargo_line_ids.mapped('cargo_category'))
        scene = self.env['tlmp.transport.scene'].browse(scene_id) if scene_id else False
        cargo_category = (
            vals.get('cargo_category') or vals.get('cargo_type')
            or (record.cargo_category if record else False)
            or (record.cargo_type if record else False))
        return {
            'scene_code': scene.code if scene else (
                record.scene_id.code if record and record.scene_id else False),
            'business_driver': vals.get(
                'business_driver', record.business_driver if record else 'plan_driven'),
            'cargo_category': cargo_category or 'piece',
            'carrier_type': vals.get(
                'carrier_type', record.carrier_type if record else 'truck'),
            't1_attribute': vals.get(
                't1_attribute', record.t1_attribute if record else 'normal'),
            'dg_attribute': vals.get(
                'dg_attribute', record.dg_attribute if record else 'normal'),
            'carrier_capabilities': capabilities,
            'mixed_roots': len(categories) > 1,
            'vehicle_requirement_mode': (
                vals.get('vehicle_requirement_mode')
                or self._get_vehicle_policy_mode(vals.get(
                    'carrier_type', record.carrier_type if record else 'truck'))),
            'vehicle_body_type': vals.get(
                'vehicle_body_type', record.vehicle_body_type if record else 'no_requirement'),
            'vehicle_capacity_requirement': vals.get(
                'vehicle_capacity_requirement',
                record.vehicle_capacity_requirement if record else 'no_limit'),
            'is_dangerous_goods': (
                vals.get('is_dangerous_goods')
                or (record.is_dangerous_goods if record
                    else ('adr_dangerous'
                          if vals.get('dg_attribute') == 'dg'
                          or vals.get('has_dangerous_goods') else 'normal'))),
            'has_dangerous_goods': bool(
                vals.get('has_dangerous_goods',
                         record.has_dangerous_goods if record else False)),
            'dg_adr_class': vals.get(
                'dg_adr_class', record.dg_adr_class if record else False),
            'dg_un_code': vals.get(
                'dg_un_code', record.dg_un_code if record else False),
            'assigned_vehicle_capacity': vals.get('assigned_vehicle_capacity'),
            'assigned_vehicle_body_type': vals.get('assigned_vehicle_body_type'),
            'assigned_vehicle_adr': vals.get('assigned_vehicle_adr'),
        }

    @api.depends('cargo_type')
    def _compute_cargo_category(self):
        for r in self:
            r.cargo_category = r.cargo_type or 'piece'

    @api.depends('carrier_type')
    def _compute_vehicle_requirement_mode(self):
        """Derive vehicle_requirement_mode from carrier_type via policy config."""
        for r in self:
            r.vehicle_requirement_mode = self._get_vehicle_policy_mode(r.carrier_type)

    @api.depends('has_dangerous_goods', 'dg_attribute',
                 'cargo_line_ids.has_dangerous_goods')
    def _compute_is_dangerous_goods(self):
        for r in self:
            dangerous = (r.dg_attribute == 'dg' or r.has_dangerous_goods
                         or any(line.has_dangerous_goods
                                for line in r.cargo_line_ids))
            r.is_dangerous_goods = 'adr_dangerous' if dangerous else 'normal'

    @api.constrains('is_dangerous_goods', 'dg_adr_class', 'dg_un_code')
    def _check_dangerous_goods_details(self):
        for r in self:
            if (r.is_dangerous_goods == 'adr_dangerous'
                    and not (r.dg_adr_class and r.dg_un_code)):
                raise ValidationError(
                    _('ADR 危险品需求必须填写 ADR Class 和 UN Code。'))
            if (r.is_dangerous_goods == 'normal'
                    and (r.dg_adr_class or r.dg_un_code)):
                raise ValidationError(
                    _('普通货物不允许填写 ADR Class / UN Code。'))

    @api.depends('scene_id.code', 'business_driver', 'cargo_category',
                 'carrier_type', 't1_attribute', 'dg_attribute')
    def _compute_matrix_code(self):
        for r in self:
            r.matrix_code = '-'.join([
                SCENE_S_CODES.get(r.scene_id.code, 'S0') if r.scene_id else 'S0',
                BUSINESS_DRIVER.get(r.business_driver, 'B0'),
                CARGO_CATEGORY.get(r.cargo_category, 'C0'),
                CARRIER_TYPE.get(r.carrier_type, 'D0'),
                T1_ATTRIBUTE.get(r.t1_attribute, 'E0'),
                DG_ATTRIBUTE.get(r.dg_attribute, 'F0'),
            ])

    def _matrix_context(self):
        capabilities = set()
        if self.carrier_id:
            capabilities = set(self.carrier_id.carrier_capability_ids.mapped('code'))
        categories = set(self.cargo_line_ids.mapped('cargo_category'))
        return {
            'scene_code': self.scene_id.code if self.scene_id else False,
            'business_driver': self.business_driver,
            'cargo_category': self.cargo_category,
            'carrier_type': self.carrier_type,
            't1_attribute': self.t1_attribute,
            'dg_attribute': self.dg_attribute,
            'carrier_capabilities': capabilities,
            'mixed_roots': len(categories) > 1,
            'vehicle_requirement_mode': self.vehicle_requirement_mode,
            'vehicle_body_type': self.vehicle_body_type,
            'vehicle_capacity_requirement': self.vehicle_capacity_requirement,
            'is_dangerous_goods': self.is_dangerous_goods,
            'has_dangerous_goods': self.has_dangerous_goods,
            'dg_adr_class': self.dg_adr_class,
            'dg_un_code': self.dg_un_code,
        }

    @api.depends('scene_id.code', 'business_driver', 'cargo_category',
                 'carrier_type', 't1_attribute', 'dg_attribute',
                 'carrier_id.carrier_capability_ids',
                 'cargo_line_ids.cargo_category',
                 'vehicle_requirement_mode', 'vehicle_body_type',
                 'vehicle_capacity_requirement', 'is_dangerous_goods',
                 'has_dangerous_goods', 'dg_adr_class', 'dg_un_code')
    def _compute_matrix_validation(self):
        for r in self:
            res = BusinessMatrixEngine.validate(self.env, r._matrix_context())
            r.matrix_validation_result = res['result']
            r.matrix_validation_violations = json.dumps(
                res['violations'], ensure_ascii=False)


    def _build_vehicle_requirement_snapshot(self):
        return json.dumps({
            'vehicle_requirement_mode': self.vehicle_requirement_mode,
            'vehicle_requirement_mode_snapshot': self.vehicle_requirement_mode_snapshot,
            'vehicle_body_type': self.vehicle_body_type,
            'vehicle_capacity_requirement': self.vehicle_capacity_requirement,
            'is_dangerous_goods': self.is_dangerous_goods,
            'dg_adr_class': self.dg_adr_class,
            'dg_un_code': self.dg_un_code,
            'vehicle_requirement_validation_result': self.vehicle_requirement_validation_result,
            'violations': json.loads(self.vehicle_requirement_validation_violations or '[]'),
        }, ensure_ascii=False)

    def _freeze_vehicle_requirement_snapshot(self):
        self.write({
            'vehicle_requirement_snapshot_status': 'frozen',
            'vehicle_requirement_snapshot': self._build_vehicle_requirement_snapshot(),
        })

    # -----------------------------------------------------------
    # State transitions
    # -----------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft requests can be confirmed.'))
        self.write({'vehicle_requirement_mode_snapshot': self.vehicle_requirement_mode})
        self._freeze_vehicle_requirement_snapshot()
        self.env['tlmp.workflow.engine'].transition(
            self, 'confirmed', 'REQUEST_CONFIRMED',
            extra_vals={
                'matrix_snapshot_status': 'frozen',
                'validation_state': 'passed',
            })
        return True

    def action_submit(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft requests can be submitted.'))
        if self.matrix_validation_result == 'block':
            raise UserError(_('Cannot submit: Business Matrix BLOCK.'))
        if self.vehicle_requirement_validation_result == 'block':
            raise UserError(_('Cannot submit: Vehicle Requirement BLOCK.'))
        self.write({'vehicle_requirement_mode_snapshot': self.vehicle_requirement_mode})
        self._freeze_vehicle_requirement_snapshot()
        self.env['tlmp.workflow.engine'].transition(
            self, 'submitted', 'REQUEST_SUBMITTED',
            extra_vals={
                'matrix_snapshot_status': 'frozen',
                'validation_state': 'passed',
            })
        return True

    def action_process(self):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('Only submitted requests can be processed.'))
        if self.validation_state != 'passed':
            raise UserError(
                _('Request validation_state must be passed before processing.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'processing', 'REQUEST_PROCESSING')
        return True

    def action_complete(self):
        self.ensure_one()
        if self.state != 'processing':
            raise UserError(_('Only processing requests can be completed.'))
        if self.total_order_count and self.closed_order_count < self.total_order_count:
            raise UserError(
                _('All orders must be closed before request completion.'))
        fulfillment = ('partial'
                       if self.ordered_qty and self.delivered_qty < self.ordered_qty
                       else 'completed')
        self.env['tlmp.workflow.engine'].transition(
            self, 'completed', 'REQUEST_COMPLETED',
            extra_vals={'fulfillment_status': fulfillment})
        return True

    def action_cancel(self):
        engine = self.env['tlmp.workflow.engine']
        for r in self:
            if r.state in ('completed', 'cancelled'):
                raise UserError(_('Request is already in a final state.'))
            engine.transition(
                r, 'cancelled', 'REQUEST_CANCELLED',
                extra_vals={'fulfillment_status': 'cancelled'})
        return True

    # -----------------------------------------------------------
    # Plan-Driven flow: Schedule
    # -----------------------------------------------------------
    def action_go_schedule(self):
       self.ensure_one()
       if self.request_type != 'plan_driven':
           raise UserError(_('Schedule is only available for plan-driven requests.'))
       # Reuse existing Pickup Plan if already created
       # Reuse existing Pickup Plan (search by request_id or name)
       plan_name = self.name.replace('REQ', 'PUP-')
       existing_plan = self.env['pickup.plan'].search([
           '|',
           ('transport_request_id', '=', self.id),
           ('name', '=', plan_name),
       ], limit=1)
       
       if existing_plan:
           plan = existing_plan
           # Update transport_request_id if not set (first-time fix)
           if not plan.transport_request_id:
               plan.transport_request_id = self.id
       else:
           # Create a new Pickup Plan
           plan = self.env['pickup.plan'].create({
               'name': plan_name,
               'transport_request_id': self.id,
               'scene_id': self.scene_id.id,
               'cargo_type': self.cargo_type,
               'destination_type': self.destination_type,
               'terminal_id': self.terminal_id.id,
               'warehouse_id': self.warehouse_id.id,
               'source_type': 'manual',
               # Sprint45: copy address snapshot from request
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
           })
           # Copy cargo lines to pickup plan container lines
           for cl in self.cargo_line_ids:
               self.env['pickup.plan.container.line'].create({
                   'plan_id': plan.id,
                   'container_number': cl.container_no or '',
                   'container_type': cl.container_type or '20GP',
                   'bl_number': cl.bl_number or '',
                   'weight': cl.gross_weight,
               })
       
       return {
           'type': 'ir.actions.client',
           'tag': 'tlmp_schedule.action',
           'target': 'self',
       }

    # -----------------------------------------------------------
    # Plan-Driven flow: Create Transport Order
    # -----------------------------------------------------------
    def action_create_transport_order(self):
       self.ensure_one()
       if self.request_type != 'plan_driven':
           raise UserError(_('Direct order creation is for plan-driven requests only.'))
       type_map = {
           'warehouse': 'port_to_warehouse',
           'warehouse_transfer': 'warehouse_transfer',
           'customer': 'to_customer', 'self_pickup': 'to_customer',
       }
       tr_type = type_map.get(self.destination_type, 'port_to_warehouse')
       order = self.env['tlmp.transport.order'].create({
           'transport_type_id': self.env['tlmp.transport.type']._get_by_code(tr_type).id,
           'fleet_operation_mode': 'subcontracted',
           'partner_id': self.partner_id.id or self.env.user.partner_id.id,
           'carrier_id': self.carrier_id.id if self.carrier_id else False,
           'cargo_description': self.cargo_description or _('Request %s') % self.name,
           'cargo_weight': self.cargo_weight, 'cargo_volume': self.cargo_volume,
           'pallet_count': self.pallet_count, 'package_count': self.package_count,
           'planned_pickup_date': self.planned_pickup_date or self.requested_pickup_date,
           'driver_name': self.driver_name, 'driver_phone': self.driver_phone,
           'vehicle_plate': self.vehicle_plate, 'notes': self.special_requirements,
       })
       return {
           'type': 'ir.actions.act_window',
           'res_model': 'tlmp.transport.order', 'view_mode': 'form',
           'res_id': order.id, 'target': 'current',
       }

    # -----------------------------------------------------------
    # Commercial flow: Start Inquiry
    # -----------------------------------------------------------
    def action_start_inquiry(self):
       self.ensure_one()
       if self.request_type != 'commercial':
           raise UserError(_('Inquiry is only available for commercial requests.'))
       if self.has_accepted_quote:
           raise UserError(_('This request already has an accepted quote. Start a new inquiry only after the quote is rejected or cancelled.'))
       cargo_summary = self.cargo_description
       cargo_lines = self.cargo_line_ids
       if not cargo_summary and cargo_lines:
           cargo_summary = '\n'.join(
               ' - '.join(x for x in (cl.description, cl.container_no, cl.bl_number) if x)
               for cl in cargo_lines)
       if not cargo_summary and self.cargo_type == 'pallet':
           cargo_summary = _('Pallet %s / Package %s') % (
               self.pallet_count or 0, self.package_count or 0)
       if not cargo_lines and self.cargo_type == 'pallet':
           inquiry_lines = [(0, 0, {
               'description': cargo_summary,
               'quantity': self.pallet_count or 1.0,
           })]
       elif not cargo_lines and self.cargo_type == 'piece':
           inquiry_lines = [(0, 0, {
               'description': _('Pieces %s') % (self.package_count or 0),
               'quantity': self.package_count or 1.0,
           })]
       else:
           inquiry_lines = [(0, 0, {
               'description': cl.description or cl.container_no or cl.bl_number or _('Cargo'),
               'quantity': 1.0,
           }) for cl in cargo_lines]
       inquiry = self.env['tlmp.transport.inquiry'].create({
           'request_id': self.id,
           'partner_id': self.carrier_id.id if self.carrier_id else False,
           'cargo_summary': cargo_summary or '',
           'weight_kg': self.cargo_weight or sum(cl.gross_weight for cl in cargo_lines),
           'volume_m3': self.cargo_volume or sum(cl.volume_m3 for cl in cargo_lines),
           'pickup_date': self.requested_pickup_date,
           'line_ids': inquiry_lines,
       })
       return {
           'type': 'ir.actions.act_window',
           'res_model': 'tlmp.transport.inquiry', 'view_mode': 'form',
           'res_id': inquiry.id, 'target': 'current',
       }

    # -----------------------------------------------------------

    # -----------------------------------------------------------
    # Commercial flow: Create Orders from Accepted Quotes
    # -----------------------------------------------------------
    def action_create_orders_from_quotes(self):
       self.ensure_one()
       if self.request_type != 'commercial':
          raise UserError(_('This action is only available for commercial requests.'))
       accepted = self.quote_ids.filtered(lambda q: q.state == 'accepted')
       if not accepted:
          raise UserError(_('No accepted quotes found.'))
       existing_ids = accepted.mapped('transport_order_id').ids
       created = []
       for quote in accepted:
          if not quote.transport_order_id:
              order = quote._auto_create_order()
              created.append(order.id)
       target_ids = existing_ids + created
       if target_ids:
          if len(target_ids) == 1:
              return {'type': 'ir.actions.act_window', 'res_model': 'tlmp.transport.order',
                      'view_mode': 'form', 'res_id': target_ids[0], 'target': 'current'}
          return {'type': 'ir.actions.act_window', 'res_model': 'tlmp.transport.order',
                  'view_mode': 'list', 'domain': [('id', 'in', target_ids)], 'target': 'current'}
       return {'type': 'ir.actions.act_window', 'res_model': 'tlmp.transport.request', 'view_mode': 'form', 'res_id': self.id}


    # Constraints
    # -----------------------------------------------------------
    @api.onchange('scene_id')
    def _onchange_scene_id(self):
        for rec in self:
            if not rec.scene_id:
                continue
            scene = rec.scene_id
            rec.destination_type = 'warehouse_transfer' if scene.code == 'warehouse_transfer' else scene.destination_type
            rec.request_type = 'plan_driven' if scene.scene_type in ('plan_driven', 'mixed') else 'commercial'
            rec.business_driver = rec.request_type
            if scene.destination_type == 'customer':
                rec.warehouse_id = False
            else:
                rec.partner_id = False

    @api.onchange('terminal_id')
    def _onchange_terminal_id(self):
        for r in self:
            if r.terminal_id and not r.origin_street:
                r.origin_street = r.terminal_id.street
                r.origin_zip = r.terminal_id.zip
                r.origin_city = r.terminal_id.city
                r.origin_state_id = r.terminal_id.state_id
                r.origin_country_id = r.terminal_id.country_id

    @api.onchange('carrier_id')
    def _onchange_carrier_id(self):
        for r in self:
            if r.carrier_id:
                partner_type = r.carrier_id.carrier_type
                r.carrier_type = {
                    'own_fleet': 'own_fleet',
                    'contracted': 'truck',
                    'subcontracted': 'truck',
                }.get(partner_type, 'truck')

    @api.onchange('source_warehouse_id')
    def _onchange_source_warehouse_id(self):
        for r in self:
            wh = r.source_warehouse_id
            if wh and wh.partner_id and not r.origin_street:
                r.origin_street = wh.partner_id.street
                r.origin_zip = wh.partner_id.zip
                r.origin_city = wh.partner_id.city
                r.origin_state_id = wh.partner_id.state_id
                r.origin_country_id = wh.partner_id.country_id

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for r in self:
            if r.partner_id and not r.destination_street and r.scene_id and r.scene_id.destination_type == 'customer':
                r.destination_street = r.partner_id.street
                r.destination_zip = r.partner_id.zip
                r.destination_city = r.partner_id.city
                r.destination_state_id = r.partner_id.state_id
                r.destination_country_id = r.partner_id.country_id

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        for r in self:
            if r.warehouse_id and not r.destination_street:
                wh = r.warehouse_id
                if wh.partner_id:
                    r.destination_street = wh.partner_id.street
                    r.destination_zip = wh.partner_id.zip
                    r.destination_city = wh.partner_id.city
                    r.destination_state_id = wh.partner_id.state_id
                    r.destination_country_id = wh.partner_id.country_id

    @api.onchange('cargo_line_ids')
    def _onchange_cargo_line_totals(self):
        for r in self:
            pallet_count, package_count, weight, volume = r._get_cargo_totals(
                update_lines=True)
            r.pallet_count = pallet_count
            r.package_count = package_count
            r.cargo_weight = weight
            r.cargo_volume = volume

    def _get_cargo_totals(self, update_lines=False):
        """Roll up cargo node totals for the request header."""
        pallet_count = 0
        package_count = 0
        weight = 0.0
        volume = 0.0
        for line in self.cargo_line_ids:
            level = line.packaging_level or 'piece'
            line_weight = 0.0
            line_volume = 0.0
            if level == 'handling_unit':
                line_packages = int(round(
                    (line.qty or 0.0) * (line.pieces_per_pallet or 0)))
                line_weight = (
                    (line.qty or 0.0) * (line.pallet_gross_weight_kg or 0.0))
                line_volume = (
                    (line.qty or 0.0) * (line.pallet_volume_m3 or 0.0))
                pallet_count += line.qty or 0.0
                package_count += line_packages
            elif level in ('package', 'piece'):
                line_packages = int(round(line.qty or 0.0))
                line_weight = (
                    (line.qty or 0.0) * (line.piece_gross_weight_kg or 0.0))
                line_volume = (
                    (line.qty or 0.0) * (line.piece_volume_m3 or 0.0))
                package_count += line.qty or 0.0
            else:  # container leaf: manual equipment totals
                line_packages = 0
                line_weight = line.gross_weight or 0.0
                line_volume = line.volume_m3 or 0.0
            if update_lines:
                line.packages = line_packages
                line.gross_weight = line_weight
                line.volume_m3 = line_volume
            if line.child_cargo_line_ids:
                continue
            weight += line_weight
            volume += line_volume
        return int(round(pallet_count)), int(round(package_count)), weight, volume

    @api.constrains('scene_id', 'destination_type', 'warehouse_id', 'source_warehouse_id', 'partner_id', 'destination_street')
    def _check_destination_fields(self):
       for rec in self:
           scene = rec.scene_id
           dest = scene.destination_type if scene else rec.destination_type
           if dest == 'warehouse' or (not scene and rec.destination_type == 'warehouse_transfer'):
               if not rec.warehouse_id:
                   raise UserError(_('Destination Warehouse required for warehouse/transfer.'))
           if (scene and scene.code == 'warehouse_transfer') or (not scene and rec.destination_type == 'warehouse_transfer'):
               if not rec.source_warehouse_id:
                   raise UserError(_('Source Warehouse required for warehouse transfer.'))
           if dest in ('customer', 'self_pickup') and not rec.partner_id and not rec.destination_street:
               raise UserError(_('Customer or Destination Address required for delivery/self-pickup.'))

    # -----------------------------------------------------------
    # IFFM reference (read-only soft link)
    # -----------------------------------------------------------
    @api.model
    def _get_reference_models(self):
       models = []
       if self.env.get('import.pickup.requirement'):
           models.append(('import.pickup.requirement', 'Import Pickup Requirement'))
       return models

    iff_requirement_ref = fields.Reference(
       selection=lambda self: self._get_reference_models(),
       string='IFF Pickup Requirement',
       help='Read-only reference to import.pickup.requirement (wd_iffm). No hard dependency.')

    # ---- Onchange: auto-fill from IFFM reference ----
    @api.onchange('iff_requirement_ref')
    def _onchange_iff_requirement_ref(self):
       if not self.iff_requirement_ref:
           return
       req = self.iff_requirement_ref
       if req._name != 'import.pickup.requirement':
           return
       self.source_type = 'iff'
       self.terminal_id = req.terminal_a if hasattr(req, 'terminal_a') else False
       if req.pickup_scene == 'to_our_warehouse' and req.warehouse_id:
           self.destination_type = 'warehouse'
           self.warehouse_id = req.warehouse_id
       elif req.pickup_scene == 'to_customer_address':
           self.destination_type = 'customer'
           self.delivery_address = (req.delivery_street or '') + ', ' + (req.delivery_zip or '') + ' ' + (req.delivery_city or '')
           self.delivery_contact = req.delivery_contact_id.display_name if req.delivery_contact_id else ''
           self.delivery_phone = req.delivery_phone or ''
       elif req.pickup_scene == 'customer_self_pickup':
           self.destination_type = 'self_pickup'
           self.delivery_contact = req.self_pickup_contact_id.display_name if req.self_pickup_contact_id else ''
           self.delivery_phone = req.self_pickup_phone or ''
       self.request_type = 'plan_driven' if self.destination_type in ('warehouse', 'warehouse_transfer') else 'commercial'
