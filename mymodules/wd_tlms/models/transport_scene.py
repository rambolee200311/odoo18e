# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class TransportScene(models.Model):
    _name = 'tlmp.transport.scene'
    _description = 'Transport Scene'
    _order = 'sequence, id'
    _rec_name = 'name'

    name = fields.Char(string='Scene Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True, index=True)
    scene_type = fields.Selection([
        ('plan_driven', 'Plan-Driven'),
        ('commercial', 'Commercial'),
        ('mixed', 'Mixed'),
    ], string='Scene Type', required=True, default='plan_driven')
    origin_type = fields.Selection([
        ('terminal', 'Terminal'),
        ('warehouse', 'Warehouse'),
        ('customer', 'Customer'),
        ('depot', 'Depot / Container Yard'),
    ], string='Origin Type', required=True, default='terminal',
       help='What type of location is the origin of this transport scene')
    destination_type = fields.Selection([
        ('warehouse', 'Warehouse'),
        ('customer', 'Customer'),
    ], string='Destination Type', required=True, default='warehouse',
       help='What type of location is the destination of this transport scene')
    creation_method = fields.Selection([
        ('manual', 'Manual'),
        ('quote_auto', 'Quote Auto'),
    ], string='Creation Method', default='manual')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')

    # Sprint40: flow + destination validation
    allowed_flow_ids = fields.Many2many(
        'tlmp.transport.flow.type', string='Allowed Flow Types',
        help='Request types this scene supports (e.g. plan_driven, commercial)')
    allowed_destination_ids = fields.Many2many(
        'tlmp.transport.destination.type', string='Allowed Destination Types',
        help='Destination types this scene supports (e.g. warehouse, customer)')
    default_transport_type_id = fields.Many2one(
        'tlmp.transport.type', string='Default Transport Type',
        help='Default transport type for this scene (reduces hardcoded mapping)')

    event_path_ids = fields.One2many(
        'tlmp.transport.scene.event', 'scene_id',
        string='Scene-Event Paths')

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', _('Scene code must be unique!')),
    ]


class TransportEventType(models.Model):
    _name = 'tlmp.transport.event.type'
    _description = 'Transport Event Type'
    _order = 'sequence_order, id'
    _rec_name = 'name'

    name = fields.Char(string='Event Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True, index=True)
    is_base_event = fields.Boolean(
        string='Base Event',
        help='Base events are subject to sequential ordering constraints')
    sequence_order = fields.Integer(
        string='Sequence Order',
        help='Ordering position for base events')
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')

    _sql_constraints = [
        ('code_unique2', 'UNIQUE(code)', _('Event type code must be unique!')),
    ]

    def get_label(self):
        return self.name or self.code


class TransportSceneEvent(models.Model):
    _name = 'tlmp.transport.scene.event'
    _description = 'Scene-Event Path'
    _order = 'scene_id, sequence, id'
    _rec_name = 'display_name'

    scene_id = fields.Many2one('tlmp.transport.scene', string='Scene',
                               required=True, ondelete='cascade')
    event_type_id = fields.Many2one('tlmp.transport.event.type', string='Event Type',
                                    required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10,
                              help='Event ordering within this scene')
    is_mandatory = fields.Boolean(string='Mandatory', default=False)
    pod_required = fields.Boolean(string='POD Required', default=False)
    active = fields.Boolean(string='Active', default=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name')

    @api.depends('scene_id', 'event_type_id')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s → %s' % (r.scene_id.name, r.event_type_id.name)
