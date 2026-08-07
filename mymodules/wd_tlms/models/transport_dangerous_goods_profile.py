# -*- coding: utf-8 -*-
from odoo import models, fields


class TransportDangerousGoodsProfile(models.Model):
    _name = 'tlmp.transport.dangerous.goods.profile'
    _description = 'Dangerous Goods Profile - ADR Attribute Template'
    _rec_name = 'name'

    name = fields.Char(string='Profile Name', required=True)
    un_dictionary_id = fields.Many2one(
        'tlmp.transport.un.dictionary', string='UN Entry',
        required=True, ondelete='restrict')
    # Related fields from UN dictionary (read-only references)
    un_number = fields.Char(related='un_dictionary_id.un_number', string='UN Number', readonly=True)
    proper_shipping_name = fields.Char(related='un_dictionary_id.proper_shipping_name',
                                       string='Proper Shipping Name', readonly=True)
    hazard_class = fields.Char(related='un_dictionary_id.hazard_class', string='Class', readonly=True)
    classification_code = fields.Char(related='un_dictionary_id.classification_code',
                                      string='Classification Code', readonly=True)
    packing_group = fields.Selection(related='un_dictionary_id.packing_group',
                                     string='Packing Group', readonly=True)
    tunnel_code = fields.Char(related='un_dictionary_id.tunnel_code', string='Tunnel Code', readonly=True)
    transport_category = fields.Char(related='un_dictionary_id.transport_category',
                                     string='Transport Category', readonly=True)
    special_provision = fields.Char(related='un_dictionary_id.special_provision',
                                    string='Special Provision', readonly=True)
    is_active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Profile name must be unique!'),
    ]
