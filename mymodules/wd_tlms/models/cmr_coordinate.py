# -*- coding: utf-8 -*-
from odoo import models, fields


class CMRCoordinate(models.Model):
    _name = 'tlmp.cmr.coordinate'
    _description = 'CMR XY Coordinate Configuration'
    _order = 'section, sequence, id'
    _rec_name = 'name'

    name = fields.Char(string='Coordinate Name', required=True)
    field_identifier = fields.Char(
        string='Field Identifier', required=True,
        help='Field identifier used in the report template to look up this coordinate')
    section = fields.Selection([
        ('header', 'Header'),
        ('sender', 'Sender'),
        ('consignee', 'Consignee'),
        ('transit', 'Transit'),
        ('carrier', 'Carrier'),
        ('cargo_table', 'Cargo Table'),
        ('footer', 'Footer'),
    ], string='Section', required=True, default='header')
    sequence = fields.Integer(string='Sequence', default=10)
    x_mm = fields.Float(string='X Offset (mm)', required=True, default=0.0,
                        help='Distance from left edge of paper in mm')
    y_mm = fields.Float(string='Y Offset (mm)', required=True, default=0.0,
                        help='Distance from top edge of paper in mm')
    font_size = fields.Integer(string='Font Size', default=10)
    alignment = fields.Selection([
        ('left', 'Left'),
        ('center', 'Center'),
        ('right', 'Right'),
    ], string='Alignment', default='left')
    max_length = fields.Integer(string='Max Characters', default=0,
                                help='0 = unlimited')
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')
