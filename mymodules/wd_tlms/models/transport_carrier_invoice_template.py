# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import json


class CarrierInvoiceTemplate(models.Model):
    """Carrier Invoice Template — Field transformation rules for external invoice intake.
    Maps carrier invoice columns (CSV/XLSX) to billing document fields.
    Target fields are whitelist-only — no model methods or arbitrary eval."""
    _name = 'tlmp.carrier.invoice.template'
    _description = 'Carrier Invoice Template'
    _rec_name = 'name'

    name = fields.Char(string='Template Name', required=True)
    carrier_profile_id = fields.Many2one(
        'tlmp.carrier.profile', string='Carrier Profile', required=True)
    file_type = fields.Selection([
        ('csv', 'CSV'),
        ('xlsx', 'Excel (.xlsx)'),
    ], string='File Type', required=True, default='csv')
    mapping_json = fields.Text(
        string='Mapping Config (JSON)',
        required=True,
        help='Field transformation rules. JSON array of {source_column, target_field, transform}. '
             'Allowed target_fields: external_invoice_no, invoice_version, document_no, '
             'carrier_reference, service_date, raw_description, net_amount, tax, line_total, '
             'charge_type_code, raw_reference, document_type, billing_period_start, '
             'billing_period_end. Forbidden: model_method, python_expression, arbitrary_eval. '
             'Allowed transform: char, decimal, integer, date, datetime, boolean, currency')
    encoding = fields.Selection([
        ('utf-8', 'UTF-8'),
        ('gbk', 'GBK'),
        ('iso-8859-1', 'ISO-8859-1'),
        ('auto', 'Auto Detect'),
    ], string='Encoding', default='auto')
    delimiter = fields.Char(string='CSV Delimiter', default=',')
    has_header = fields.Boolean(string='Has Header Row', default=True)
    is_active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    ALLOWED_TARGET_FIELDS = {
        'external_invoice_no', 'invoice_version', 'document_no',
        'carrier_reference', 'service_date', 'raw_description',
        'net_amount', 'tax', 'line_total', 'charge_type_code',
        'raw_reference', 'document_type',
        'billing_period_start', 'billing_period_end',
    }
    ALLOWED_TRANSFORM_TYPES = {'char', 'decimal', 'integer', 'date', 'datetime', 'boolean', 'currency'}

    _sql_constraints = [
        ('name_carrier_unique',
         'unique(name, carrier_profile_id, company_id)',
         'Template name must be unique per carrier.'),
    ]

    @api.constrains('mapping_json')
    def _check_mapping_json(self):
        for r in self:
            if not r.mapping_json:
                continue
            try:
                rules = json.loads(r.mapping_json)
                if isinstance(rules, dict):
                    rules = [rules]
                if not isinstance(rules, list):
                    raise ValueError(_('Mapping must be a JSON array or object'))
                for rule in rules:
                    col = rule.get('source_column')
                    field = rule.get('target_field')
                    xform = rule.get('transform', 'char')
                    if not col or not field:
                        raise ValueError(_('Each mapping rule requires source_column and target_field'))
                    if field not in r.ALLOWED_TARGET_FIELDS:
                        raise ValueError(_('Target field "%s" not in whitelist.') % field)
                    if xform not in r.ALLOWED_TRANSFORM_TYPES:
                        raise ValueError(_('Transform type "%s" not allowed.') % xform)
            except json.JSONDecodeError:
                raise models.ValidationError(_('Mapping JSON is not valid JSON'))
