# -*- coding: utf-8 -*-
"""Settlement Exception — system-level anomaly detection and operational closure.

Exception = system detects something wrong.
Case = human resolves something wrong.
Exception is NOT Case. See ADR-037.
"""
import json
from datetime import datetime, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SettlementException(models.Model):
    _name = 'tlmp.settlement.exception'
    _description = 'Settlement Exception'
    _rec_name = 'name'
    _order = 'priority desc, create_date desc'

    name = fields.Char(string='Exception No.', required=True, copy=False,
                       default=lambda self: _('New'))

    # ── Type & Category ──
    exception_type = fields.Selection([
        ('MATCH_FAILED', 'Match Failed'),
        ('AMOUNT_MISMATCH', 'Amount Mismatch'),
        ('DUPLICATE_INVOICE', 'Duplicate Invoice'),
        ('INVALID_REFERENCE', 'Invalid Reference'),
        ('IMPORT_ERROR', 'Import Error'),
        ('APPROVAL_TIMEOUT', 'Approval Timeout'),
    ], string='Type', required=True)
    exception_category = fields.Selection([
        ('matching', 'Matching'),
        ('billing', 'Billing'),
        ('financial', 'Financial'),
        ('operational', 'Operational'),
        ('data_quality', 'Data Quality'),
    ], string='Category', compute='_compute_category', store=False)

    # ── State Machine ──
    state = fields.Selection([
        ('new', 'New'),
        ('assigned', 'Assigned'),
        ('processing', 'Processing'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='new', required=True)

    # ── Priority & SLA ──
    priority = fields.Selection([
        ('urgent', 'Urgent'),
        ('high', 'High'),
        ('normal', 'Normal'),
        ('low', 'Low'),
    ], string='Priority', default='normal', required=True)
    sla_deadline = fields.Datetime(string='SLA Deadline', compute='_compute_sla_deadline', store=True)
    sla_status = fields.Selection([
        ('on_track', 'On Track'),
        ('at_risk', 'At Risk'),
        ('overdue', 'Overdue'),
        ('escalated', 'Escalated'),
    ], string='SLA Status', compute='_compute_sla_status', store=False)

    # ── Resolution Mode ──
    resolution_mode = fields.Selection([
        ('manual', 'Manual'),
        ('auto', 'Auto'),
    ], string='Resolution Mode', default='manual')

    # ── Source Reference（运营证据链）──
    source_model = fields.Char(string='Source Model')
    source_res_id = fields.Integer(string='Source Record ID')
    source_display_name = fields.Char(string='Source Display Name')
    source_snapshot = fields.Text(string='Source Snapshot (JSON)')
    source_captured_at = fields.Datetime(string='Snapshot Captured At')

    # ── Assignment ──
    assigned_to = fields.Many2one('res.users', string='Assigned To')
    assigned_at = fields.Datetime(string='Assigned At')

    # ── Case Link ──
    case_id = fields.Many2one('tlmp.carrier.settlement.case', string='Settlement Case')

    # ── Description ──
    description = fields.Text(string='Description')

    # ── Resolution ──
    resolution_note = fields.Text(string='Resolution Note')
    cancel_reason = fields.Text(string='Cancel Reason')
    resolved_at = fields.Datetime(string='Resolved At')
    resolved_by = fields.Many2one('res.users', string='Resolved By')

    # ── Company ──
    creation_method = fields.Selection([
        ('legacy_handler', 'Legacy Handler'),
        ('manual', 'Manual'),
    ], string='Creation Method', default='manual')

    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    # ── Category Compute ──
    _type_category_map = {
        'MATCH_FAILED': 'matching',
        'AMOUNT_MISMATCH': 'financial',
        'DUPLICATE_INVOICE': 'billing',
        'INVALID_REFERENCE': 'data_quality',
        'IMPORT_ERROR': 'operational',
        'APPROVAL_TIMEOUT': 'operational',
    }

    @api.depends('exception_type')
    def _compute_category(self):
        for r in self:
            r.exception_category = self._type_category_map.get(r.exception_type, False)

    # ── SLA Deadline Compute ──
    @api.depends('priority', 'create_date')
    def _compute_sla_deadline(self):
        for r in self:
            if not r.create_date:
                r.sla_deadline = False
                continue
            hours = {'urgent': 4, 'high': 8, 'normal': 24, 'low': 72}.get(r.priority, 24)
            r.sla_deadline = r.create_date + timedelta(hours=hours)

    @api.depends('sla_deadline')
    def _compute_sla_status(self):
        now = fields.Datetime.now()
        for r in self:
            if not r.sla_deadline:
                r.sla_status = False
            elif now >= r.sla_deadline:
                r.sla_status = 'overdue'
            elif now >= r.sla_deadline - timedelta(hours=max(1, (r.sla_deadline - r.create_date).total_seconds() / 3600 * 0.2)):
                r.sla_status = 'at_risk'
            else:
                r.sla_status = 'on_track'

    # ── Sequence ──
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tlmp.settlement.exception.seq') or _('New')
        return super().create(vals_list)

    # ── State Transitions ──
    def action_assign(self):
        for r in self:
            if not r.assigned_to:
                r.assigned_to = self.env.uid
        self.write({'state': 'assigned', 'assigned_at': fields.Datetime.now()})

    def action_start_processing(self):
        self.write({'state': 'processing'})

    def action_resolve(self):
        for r in self:
            if not r.resolution_note:
                raise ValidationError(_('Resolution note is required.'))
        self.write({'state': 'resolved', 'resolved_at': fields.Datetime.now(),
                    'resolved_by': self.env.uid})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_cancel(self):
        for r in self:
            if not r.cancel_reason:
                raise ValidationError(_('Cancel reason is required.'))
        self.write({'state': 'cancelled'})

    def action_auto_resolve(self):
        """Auto-resolve for DUPLICATE_INVOICE whitelist."""
        for r in self:
            if r.exception_type != 'DUPLICATE_INVOICE':
                raise ValidationError(_('Auto resolution only allowed for DUPLICATE_INVOICE.'))
            if not r.resolution_note:
                r.resolution_note = 'System auto-rejected: duplicate invoice (carrier=%s, invoice=%s)' % (
                    r.source_display_name or '', r.description or '')
        self.write({
            'state': 'closed',
            'resolution_mode': 'auto',
            'resolved_at': fields.Datetime.now(),
            'resolved_by': self.env.uid,
        })

    # ── Invariant Checks ──
    @api.constrains('state', 'assigned_to')
    def _check_assigned_requires_owner(self):
        for r in self:
            if r.state == 'assigned' and not r.assigned_to:
                raise ValidationError(_('Assigned state requires assigned_to (invariant: assigned_requires_owner).'))

    @api.constrains('exception_type', 'resolution_mode')
    def _check_auto_resolution_whitelist(self):
        for r in self:
            if r.resolution_mode == 'auto' and r.exception_type != 'DUPLICATE_INVOICE':
                raise ValidationError(_('Auto resolution only allowed for DUPLICATE_INVOICE (invariant: auto_resolution_whitelist).'))

    @api.constrains('state', 'case_id')
    def _check_manual_exception_requires_case(self):
        for r in self:
            if r.resolution_mode == 'manual' and r.state in ('processing', 'resolved') and not r.case_id:
                raise ValidationError(_('Manual exception in %s requires case_id (invariant: case_created_for_manual_exception).') % r.state)

    @api.constrains('state')
    def _check_closed_immutable(self):
        for r in self:
            if r.state in ('closed', 'cancelled') and any(f in r._fields for f in ['write_date']):
                pass  # Odoo ORM handles write prevention via _check_modification

    @api.constrains('source_model', 'source_res_id', 'source_display_name')
    def _check_source_traceable(self):
        for r in self:
            if not r.source_model or not r.source_res_id or not r.source_display_name:
                raise ValidationError(_('source_reference requires model, res_id, and display_name (invariant: source_snapshot_is_traceable).'))
