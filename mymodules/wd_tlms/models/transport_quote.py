# -*- coding: utf-8 -*-
import json

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date


class TransportQuote(models.Model):
    _name = 'tlmp.transport.quote'
    _description = 'Transport Quote'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string='Quote No.', required=True, copy=False,
                       default=lambda self: _('New'))
    request_id = fields.Many2one('tlmp.transport.request', string='Request')
    inquiry_id = fields.Many2one('tlmp.transport.inquiry', string='Inquiry')
    partner_id = fields.Many2one('res.partner', string='Customer (Cargo Owner)')
    transport_mode = fields.Selection([('road', 'Road'), ('multimodal', 'Multimodal')],
                                      default='road')
    line_ids = fields.One2many('tlmp.transport.quote.line', 'quote_id', string='Lines')
    total_base_fee = fields.Monetary(string='Base Fee', compute='_compute_total', store=True)
    total_surcharge = fields.Monetary(string='Surcharge', compute='_compute_total', store=True)
    total_amount = fields.Monetary(string='Total', compute='_compute_total', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)
    validity_date = fields.Date(string='Valid Until')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('issued', 'Issued'),
        ('approved', 'Approved'),
        ('confirmed', 'Confirmed'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ], string='Status', default='draft', tracking=True)
    confirmation_source = fields.Selection([
        ('customer', 'Customer'),
        ('internal', 'Internal'),
        ('system', 'System'),
    ], string='Confirmation Source')
    customer_accept = fields.Boolean(string='Customer Accepted')
    notes = fields.Text(string='Notes')

    carrier_cost = fields.Monetary(string='Carrier Cost',
        help='Cost from the carrier (from accepted inquiry).')
    margin_amount = fields.Monetary(string='Margin Amount (markup)',
        compute='_compute_margin_amount', store=True,
        help='Sales margin on customer price: customer fee total - carrier cost.')
    margin_rate = fields.Float(string='Margin Rate (%)', compute='_compute_margin_rate', store=True,
        help='Sales margin on customer price: margin_amount / total_amount.')
    fee_line_ids = fields.One2many('transport.fee.line', 'source_quote_id',
        string='Fee Lines', copy=False)
    transport_order_id = fields.Many2one('tlmp.transport.order',
        string='Transport Order', readonly=True, copy=False)
    cargo_source_reference = fields.Char(
        string='Cargo Source Ref', compute='_compute_cargo_summary',
        help='Source request reference for Cargo Summary traceability.')
    cargo_summary = fields.Text(string='Cargo Summary', compute='_compute_cargo_summary')
    cargo_weight_kg = fields.Float(
        string='Cargo Weight (kg)', compute='_compute_cargo_summary')
    cargo_volume_m3 = fields.Float(
        string='Cargo Volume (m3)', compute='_compute_cargo_summary')

    # Sprint49-B: vehicle requirement display (read-only projection from request)
    vehicle_requirement_mode = fields.Selection(
        [('required', 'Required'), ('exempted', 'Exempted')],
        string='Vehicle Req. Mode', readonly=True,
        compute='_compute_vehicle_requirement_projection')
    vehicle_requirement_display = fields.Char(
        string='Vehicle Requirement', readonly=True,
        compute='_compute_vehicle_requirement_projection')
    vehicle_body_type = fields.Selection(
        related='request_id.vehicle_body_type', string='Vehicle Body Type', readonly=True)
    vehicle_capacity_requirement = fields.Selection(
        related='request_id.vehicle_capacity_requirement', string='Vehicle Capacity', readonly=True)
    is_dangerous_goods = fields.Selection(
        related='request_id.is_dangerous_goods', string='DG Vehicle Req.', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tlmp.quote.seq') or _('New')
        return super().create(vals_list)

    @api.depends('request_id.state', 'request_id.vehicle_requirement_mode',
                 'request_id.vehicle_requirement_mode_snapshot',
                 'request_id.vehicle_body_type',
                 'request_id.vehicle_capacity_requirement',
                 'request_id.is_dangerous_goods')
    def _compute_vehicle_requirement_projection(self):
        body_labels = {
            'no_requirement': '无要求', 'rear_only': '仅车尾', 'side_loading': '侧面装卸',
            'side_rear_both': '侧尾双向', 'top_loading': '顶部吊装', 'tail_lift': '液压尾板',
            'open_flatbed': '平板车', 'reefer_refrigerated': '冷藏车', 'tanker': '罐车',
        }
        capacity_labels = {
            'no_limit': '无限制', 'below_40t': '< 40t',
            '40t_44t': '40t-44t', 'over_44t': '> 44t',
        }
        dg_labels = {'normal': '普通', 'adr_dangerous': 'ADR危险品'}
        for r in self:
            req = r.request_id
            if not req:
                r.vehicle_requirement_mode = False
                r.vehicle_requirement_display = False
                continue
            r.vehicle_requirement_mode = (
                req.vehicle_requirement_mode_snapshot
                or req.vehicle_requirement_mode)
            if r.vehicle_requirement_mode == 'exempted':
                r.vehicle_requirement_display = '车辆要求：豁免'
            else:
                r.vehicle_requirement_display = '车型：%s；载重：%s；危险品：%s' % (
                    body_labels.get(req.vehicle_body_type, req.vehicle_body_type),
                    capacity_labels.get(
                        req.vehicle_capacity_requirement,
                        req.vehicle_capacity_requirement),
                    dg_labels.get(req.is_dangerous_goods, req.is_dangerous_goods))

    @api.depends('line_ids.subtotal', 'carrier_cost',
                 'fee_line_ids.party_type', 'fee_line_ids.total_amount')
    def _compute_total(self):
        for r in self:
            r.total_base_fee = sum(r.line_ids.mapped('subtotal'))
            r.total_surcharge = 0.0
            customer_fee = sum(
                r.fee_line_ids.filtered(lambda f: f.party_type == 'customer_charge')
                .mapped('total_amount'))
            r.total_amount = customer_fee if customer_fee else (r.carrier_cost or 0.0)

    @api.depends('request_id.name', 'request_id.cargo_description',
                 'request_id.cargo_weight', 'request_id.cargo_volume',
                 'inquiry_id.cargo_summary')
    def _compute_cargo_summary(self):
        for r in self:
            r.cargo_source_reference = r.request_id.name if r.request_id else False
            if r.request_id and r.request_id.cargo_description:
                r.cargo_summary = r.request_id.cargo_description
            elif r.inquiry_id:
                r.cargo_summary = r.inquiry_id.cargo_summary
            else:
                r.cargo_summary = False
            r.cargo_weight_kg = r.request_id.cargo_weight if r.request_id else 0.0
            r.cargo_volume_m3 = r.request_id.cargo_volume if r.request_id else 0.0

    @api.depends('total_amount', 'carrier_cost')
    def _compute_margin_amount(self):
        for r in self:
            r.margin_amount = (r.total_amount or 0.0) - (r.carrier_cost or 0.0)

    @api.depends('total_amount', 'margin_amount')
    def _compute_margin_rate(self):
        for r in self:
            price = r.total_amount or 0.0
            r.margin_rate = (r.margin_amount / price) if price else 0.0

    def action_accept(self):
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_('Only sent quotes can be accepted.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'accepted', 'QUOTE_ACCEPTED')
        self._auto_create_order()
        return True

    def action_send(self):
        engine = self.env['tlmp.workflow.engine']
        for rec in self:
            engine.transition(rec, 'sent', 'QUOTE_SENT')
        return True

    def action_issue(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft quotes can be issued.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'issued', 'QUOTE_ISSUED')
        return True

    def action_approve(self):
        self.ensure_one()
        if self.state != 'issued':
            raise UserError(_('Only issued quotes can be approved.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'approved', 'QUOTE_APPROVED')
        return True

    def action_confirm_customer(self, source='customer'):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved quotes can be confirmed.'))
        if not self.customer_accept:
            raise UserError(
                _('Customer acceptance is required before confirmation.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'confirmed', 'QUOTE_CONFIRMED',
            extra_vals={'confirmation_source': source})
        self._auto_create_order()
        return True

    def action_accept_from_portal(self):
        self.ensure_one()
        if self.state != 'sent':
            raise UserError(_('Quote is not in sent state.'))
        if self.validity_date and self.validity_date < fields.Date.today():
            self.env['tlmp.workflow.engine'].transition(
                self, 'expired', 'QUOTE_EXPIRED')
            raise UserError(_('Quote has expired. Please request a new quote.'))
        self.env['tlmp.workflow.engine'].transition(
            self, 'accepted', 'QUOTE_ACCEPTED')
        self._auto_create_order()
        return True

    def action_cancel(self, reason=None):
        engine = self.env['tlmp.workflow.engine']
        for rec in self:
            engine.transition(rec, 'cancelled', 'QUOTE_CANCELLED')
        return True

    def action_reject(self, reason=None):
        engine = self.env['tlmp.workflow.engine']
        for rec in self:
            engine.transition(rec, 'rejected', 'QUOTE_REJECTED')
        # Return inquiry to 'sent' state for re-quoting
        if self.inquiry_id and self.inquiry_id.state == 'accepted':
            self.inquiry_id.env['tlmp.workflow.engine'].transition(
                self.inquiry_id, 'sent', 'INQUIRY_REOPENED',
                extra_vals={'response_date': False})
        return True

    def _auto_create_order(self):
        self.ensure_one()
        request = self.request_id
        if request and request.cargo_line_ids:
            pallet_count, package_count, weight, volume = \
                request._get_cargo_totals()
            if (request.pallet_count != pallet_count
                    or request.package_count != package_count
                    or abs(request.cargo_weight - weight) > 0.005
                    or abs(request.cargo_volume - volume) > 0.005):
                raise UserError(
                    _('Request cargo totals are out of sync with cargo nodes. '
                      'Reopen the request and save it to recalculate.'))
        if request and (not request.matrix_code
                        or request.matrix_validation_result == 'block'):
            raise UserError(
                _('Business Matrix snapshot is missing or invalid. '
                  'Complete request matrix validation before creating the order.'))
        if (request and request.vehicle_requirement_mode_snapshot == 'required'
                and not request.vehicle_requirement_snapshot):
            raise UserError(
                _('Vehicle requirement snapshot is missing. '
                  'Submit/confirm the request before creating the order.'))
        order = self.env['tlmp.transport.order'].create({
            'scene_id': self.request_id.scene_id.id if self.request_id and self.request_id.scene_id else False,
            # Sprint44: copy address from request
            'origin_street': self.request_id.origin_street if self.request_id else False,
            'origin_zip': self.request_id.origin_zip if self.request_id else False,
            'origin_city': self.request_id.origin_city if self.request_id else False,
            'origin_state_id': self.request_id.origin_state_id.id if self.request_id and self.request_id.origin_state_id else False,
            'origin_country_id': self.request_id.origin_country_id.id if self.request_id and self.request_id.origin_country_id else False,
            'destination_street': self.request_id.destination_street if self.request_id else False,
            'destination_zip': self.request_id.destination_zip if self.request_id else False,
            'destination_city': self.request_id.destination_city if self.request_id else False,
            'destination_state_id': self.request_id.destination_state_id.id if self.request_id and self.request_id.destination_state_id else False,
            'destination_country_id': self.request_id.destination_country_id.id if self.request_id and self.request_id.destination_country_id else False,
            'request_id': self.request_id.id,
            'quote_id': self.id,
            'inquiry_id': self.inquiry_id.id,
            'partner_id': (self.partner_id.id or
                           (self.request_id.partner_id.id if self.request_id and self.request_id.partner_id else False) or
                           self.env.company.partner_id.id),
            'transport_type_id': self.request_id.transport_type_id.id if self.request_id and self.request_id.transport_type_id else False,
            'fleet_operation_mode': 'subcontracted',
            'total_customer_charge': self.total_amount,
            'source_amount_customer': self.total_amount,
            'cargo_description': request.cargo_description or '',
            'cargo_weight': request.cargo_weight,
            'cargo_volume': request.cargo_volume,
            'pallet_count': request.pallet_count,
            'package_count': request.package_count,
            'matrix_code': request.matrix_code,
            'matrix_version': request.matrix_version,
            'matrix_validation_result': request.matrix_validation_result,
            'matrix_snapshot': json.dumps({
                'scene': request.scene_id.code if request.scene_id else False,
                'driver': request.business_driver,
                'cargo_category': request.cargo_category,
                'carrier_type': request.carrier_type,
                't1': request.t1_attribute,
                'dg': request.dg_attribute,
                'matrix_code': request.matrix_code,
                'matrix_version': request.matrix_version,
                'validation_result': request.matrix_validation_result,
            }, ensure_ascii=False),
            'carrier_id': (self.inquiry_id.partner_id.id if self.inquiry_id and self.inquiry_id.partner_id else
                           (self.request_id.carrier_id.id if self.request_id and self.request_id.carrier_id else False)),
            'price_source': 'quote',
            'vehicle_requirement_snapshot': json.dumps({
                'vehicle_requirement_mode': request.vehicle_requirement_mode,
                'vehicle_requirement_mode_snapshot': request.vehicle_requirement_mode_snapshot,
                'vehicle_body_type': request.vehicle_body_type,
                'vehicle_capacity_requirement': request.vehicle_capacity_requirement,
                'is_dangerous_goods': request.is_dangerous_goods,
                'dg_adr_class': request.dg_adr_class,
                'dg_un_code': request.dg_un_code,
            }, ensure_ascii=False),
        })
        self.write({'transport_order_id': order.id})
        # Copy request cargo nodes as order snapshot, preserving hierarchy.
        CargoLine = self.env['tlmp.transport.cargo.line']
        old_to_new = {}
        for cl in self.request_id.cargo_line_ids:
            old_to_new[cl.id] = CargoLine.create({
                'order_id': order.id,
                'description': cl.description,
                'commodity': cl.commodity,
                'qty': cl.qty,
                'uom': cl.uom,
                'packages': cl.packages,
                'gross_weight': cl.gross_weight,
                'net_weight': cl.net_weight,
                'volume_m3': cl.volume_m3,
                'container_no': cl.container_no,
                'bl_number': cl.bl_number,
                'container_type': cl.container_type,
                'seal_no': cl.seal_no,
                'node_type': cl.node_type,
                'packaging_level': cl.packaging_level,
                'pieces_per_pallet': cl.pieces_per_pallet,
                'pallet_gross_weight_kg': cl.pallet_gross_weight_kg,
                'pallet_volume_m3': cl.pallet_volume_m3,
                'piece_gross_weight_kg': cl.piece_gross_weight_kg,
                'piece_volume_m3': cl.piece_volume_m3,
                'source_module': cl.source_module,
                'source_model': cl.source_model,
                'source_id': cl.source_id,
                'source_line_id': cl.source_line_id,
            })
        for cl in self.request_id.cargo_line_ids:
            if cl.parent_cargo_line_id:
                old_to_new[cl.id].parent_cargo_line_id = \
                    old_to_new[cl.parent_cargo_line_id.id].id
        # Copy quote fee lines onto the order; quote fee lines stay locked after accept.
        FeeLine = self.env['transport.fee.line']
        for fl in self.fee_line_ids:
            FeeLine.create({
                'fee_type_id': fl.fee_type_id.id if fl.fee_type_id else False,
                'party_type': fl.party_type,
                'partner_id': fl.partner_id.id if fl.partner_id else False,
                'source_type': fl.source_type or 'commercial',
                'source_order_id': order.id,
                'quantity': fl.quantity,
                'unit_amount': fl.unit_amount,
                'description': fl.description,
            })
        if not self.fee_line_ids:
            charge_item = self.env['world.depot.charge.item'].search([], limit=1)
            if charge_item:
                if self.partner_id:
                    FeeLine.create({
                        'fee_type_id': charge_item.id, 'source_type': 'commercial',
                        'source_order_id': order.id, 'party_type': 'customer_charge',
                        'partner_id': self.partner_id.id,
                        'unit_amount': self.total_amount, 'quantity': 1.0,
                        'description': self.name or 'Transport charge'})
                inquiry_partner = self.inquiry_id.partner_id if self.inquiry_id else False
                if inquiry_partner and (self.carrier_cost or 0.0) > 0:
                    FeeLine.create({
                        'fee_type_id': charge_item.id, 'source_type': 'commercial',
                        'source_order_id': order.id, 'party_type': 'carrier_cost',
                        'partner_id': inquiry_partner.id,
                        'unit_amount': self.carrier_cost, 'quantity': 1.0,
                        'description': (self.name or '') + ' (carrier)'})
        return order

    def _cron_expire(self):
        expired = self.search([('state', '=', 'sent'),
                               ('validity_date', '<', fields.Date.today())])
        expired.write({'state': 'expired'})
        return True


class TransportQuoteLine(models.Model):
    _name = 'tlmp.transport.quote.line'
    _description = 'Quote Line'

    quote_id = fields.Many2one('tlmp.transport.quote', string='Quote', required=True,
                               ondelete='cascade')
    description = fields.Char(string='Description', required=True)
    unit_price = fields.Monetary(string='Unit Price')
    quantity = fields.Float(string='Quantity', default=1.0)
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', store=True)
    currency_id = fields.Many2one('res.currency', related='quote_id.currency_id')

    @api.depends('unit_price', 'quantity')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = (r.unit_price or 0.0) * r.quantity
