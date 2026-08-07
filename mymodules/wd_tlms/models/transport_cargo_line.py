# -*- coding: utf-8 -*-
import math

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TransportCargoLine(models.Model):
    _name = 'tlmp.transport.cargo.line'
    _description = 'Transport Cargo Line (Snapshot)'
    _order = 'sequence, id'

    request_id = fields.Many2one('tlmp.transport.request', string='Transport Request',
                                 index=True, ondelete='cascade')
    order_id = fields.Many2one('tlmp.transport.order', string='Transport Order',
                               index=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Char(string='Description', required=True)
    commodity = fields.Char(string='Commodity')
    qty = fields.Float(string='Quantity (Units)', default=1.0,
        help='Number of units in this line, e.g. 10 pallets. '
             'The request header totals are the sum of all lines.')
    uom = fields.Char(string='UoM',
        help='Unit of Measure for Quantity, e.g. pallet, carton, piece.')
    packages = fields.Integer(string='Packages',
        help='Inner packages/parcels of this line (total for the line).')
    gross_weight = fields.Float(string='Gross Weight (kg)',
        help='Gross weight of this line (total, not per unit).')
    net_weight = fields.Float(string='Net Weight (kg)',
        help='Net weight of this line (total, not per unit).')
    volume_m3 = fields.Float(string='Volume (m3)',
        help='Volume of this line (total, not per unit).')
    container_no = fields.Char(string='Container No.',
                               help='Transport document snapshot only — does not replace container tracking master data')

    bl_number = fields.Char(string='BL Number',
                            help='Bill of Lading number for this container')
    container_type = fields.Char(string='Container Type', default='20GP',
                                 help='ISO container type code, e.g. 20GP, 40HC')
    cargo_category = fields.Selection([
        ('container', 'C1 Container'),
        ('pallet', 'C2 Pallet'),
        ('piece', 'C3 Piece'),
    ], string='Cargo Category',
       help='Business matrix dimension C; must match the request root category.')
    node_type = fields.Selection([
        ('equipment', 'Equipment'),
        ('cargo', 'Cargo'),
    ], string='Node Type', default='cargo', required=True,
       help='equipment = transport equipment node (e.g. container); '
            'cargo = cargo node (handling unit / package / piece).')
    packaging_level = fields.Selection([
        ('container', 'Container'),
        ('handling_unit', 'Handling Unit (Pallet)'),
        ('package', 'Package'),
        ('piece', 'Piece'),
    ], string='Packaging Level', default='piece',
       help='Fixed hierarchy: container -> handling_unit -> package -> piece.')
    parent_cargo_line_id = fields.Many2one(
        'tlmp.transport.cargo.line', string='Parent Cargo Node',
        index=True, ondelete='cascade')
    child_cargo_line_ids = fields.One2many(
        'tlmp.transport.cargo.line', 'parent_cargo_line_id',
        string='Child Cargo Nodes')
    seal_no = fields.Char(string='Seal No.',
        help='Container seal number (equipment node).')
    pieces_per_pallet = fields.Integer(string='Pieces per Pallet',
        help='Inner pieces of one pallet (handling unit).')
    pallet_gross_weight_kg = fields.Float(string='Pallet Gross Weight (kg)',
        help='Gross weight of one pallet (handling unit), input per pallet.')
    pallet_volume_m3 = fields.Float(string='Pallet Volume (m3)',
        help='Volume of one pallet (handling unit), input per pallet.')
    piece_gross_weight_kg = fields.Float(string='Piece Gross Weight (kg)',
        help='Gross weight of one piece/package, input per piece.')
    piece_volume_m3 = fields.Float(string='Piece Volume (m3)',
        help='Volume of one piece/package, input per piece.')
    source_module = fields.Char(string='Source Module')
    source_model = fields.Char(string='Source Model')
    source_id = fields.Integer(string='Source Record ID')
    source_line_id = fields.Integer(string='Source Line ID')
    pallets_in_container = fields.Integer(
        string='Pallets in Container', compute='_compute_pallets_in_container',
        help='Number of handling unit children of a container node.')
    equivalent_pallets = fields.Float(
        string='Equivalent Pallets', compute='_compute_equivalent_pallets',
        help='Only package/piece nodes: ceil(max(volume/limit, weight/limit)).')
    source_type = fields.Selection([
        ('manual', 'Manual Entry'),
        ('outbound_order', 'Outbound Reference'),
        ('system', 'System/API'),
    ], string='Source Type', required=True, default='manual')
    outbound_ref_id = fields.Many2one('ir.model', string='Outbound Document Ref.',
                                      help='Reference to source outbound document (model not hardcoded)')
    has_dangerous_goods = fields.Boolean(string='Has Dangerous Goods')
    dangerous_goods_profile_id = fields.Many2one(
        'tlmp.transport.dangerous.goods.profile',
        string='Dangerous Goods Profile',
        help='ADR attribute template linked to UN dictionary. '
             'NOT an ADR field expansion on cargo_line.')
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('cargo_category') and vals.get('request_id'):
                request = self.env['tlmp.transport.request'].browse(
                    vals['request_id'])
                if request:
                    vals['cargo_category'] = request.cargo_category
        return super().create(vals_list)

    @api.constrains('request_id', 'cargo_category')
    def _check_category_matches_request(self):
        for r in self:
            if (r.request_id and r.cargo_category
                    and r.request_id.cargo_category
                    and r.cargo_category != r.request_id.cargo_category):
                raise ValidationError(
                    _('Cargo line category must match request cargo category.'))

    @api.constrains('request_id', 'order_id')
    def _check_owner_exclusive(self):
        for r in self:
            if r.request_id and r.order_id:
                raise ValidationError(_('Cargo line cannot belong to both request and order.'))

    @api.depends('child_cargo_line_ids.packaging_level')
    def _compute_pallets_in_container(self):
        for r in self:
            r.pallets_in_container = len(
                r.child_cargo_line_ids.filtered(
                    lambda c: c.packaging_level == 'handling_unit'))

    @api.depends('packaging_level', 'qty', 'piece_gross_weight_kg',
                 'piece_volume_m3', 'gross_weight', 'volume_m3')
    def _compute_equivalent_pallets(self):
        params = self.env['ir.config_parameter'].sudo()
        vol_limit = float(params.get_param('tlms.pallet_volume_m3', '1.2'))
        weight_limit = float(
            params.get_param('tlms.pallet_max_weight_kg', '1000.0'))
        for r in self:
            if r.packaging_level not in ('package', 'piece'):
                r.equivalent_pallets = 0.0
                continue
            qty = r.qty or 0.0
            if r.packaging_level == 'piece':
                volume = qty * (r.piece_volume_m3 or 0.0)
                weight = qty * (r.piece_gross_weight_kg or 0.0)
            else:
                volume = r.volume_m3 or 0.0
                weight = r.gross_weight or 0.0
            if volume <= 0 and weight <= 0:
                r.equivalent_pallets = 0.0
                continue
            r.equivalent_pallets = max(
                math.ceil(volume / vol_limit) if volume else 0,
                math.ceil(weight / weight_limit) if weight else 0)

    @api.constrains('packaging_level', 'parent_cargo_line_id')
    def _check_hierarchy_level(self):
        allowed_parents = {
            'container': (False,),
            'handling_unit': ('container',),
            'package': ('handling_unit',),
            'piece': ('package', 'handling_unit'),
        }
        for r in self:
            parent = r.parent_cargo_line_id
            if r.packaging_level == 'container' and parent:
                raise ValidationError(
                    _('Container node cannot have a parent cargo node.'))
            if parent and parent.packaging_level not in allowed_parents.get(
                    r.packaging_level, ()):
                raise ValidationError(
                    _('Invalid parent packaging level %s for %s node.')
                    % (parent.packaging_level, r.packaging_level))

    def copy_to_order(self, order):
        """Copy this cargo line to an order, creating an independent record."""
        self.ensure_one()
        new = self.copy(default={'request_id': False, 'order_id': order.id})
        return new


class TransportSceneCargoRule(models.Model):
    _name = 'tlmp.transport.scene.cargo.rule'
    _description = 'Scene Cargo Rule'
    _rec_name = 'scene_id'

    scene_id = fields.Many2one('tlmp.transport.scene', string='Scene',
                               required=True, ondelete='cascade')
    allowed_source_type = fields.Selection([
        ('manual', 'Manual Only'),
        ('outbound_order', 'Outbound Only'),
        ('both', 'Manual + Outbound'),
        ('none', 'No Cargo'),
    ], string='Allowed Source', required=True, default='manual')
    container_required = fields.Boolean(string='Container Required', default=False)
    cargo_required = fields.Boolean(string='Cargo Required', default=True)
    priority = fields.Integer(string='Priority', default=10)
    condition_domain = fields.Char(string='Condition Domain',
                                   help='Reserved for future use. Not evaluated in Sprint22.')
    active = fields.Boolean(string='Active', default=True)
