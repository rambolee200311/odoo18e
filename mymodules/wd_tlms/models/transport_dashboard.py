# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta


class TransportDashboardService(models.AbstractModel):
    _name = 'tlmp.transport.dashboard.service'
    _description = 'Transport Dashboard Service (AbstractModel, no DB table)'

    def get_event_timeout_summary(self):
        """Return dict with count + record list of overdue transport events.
        Rule: event_state not in (completed,cancelled,skipped) AND planned_time < now"""
        domain = [
            ('event_state', 'not in', ('completed', 'cancelled', 'skipped')),
            ('planned_time', '<', fields.Datetime.to_string(datetime.now())),
        ]
        events = self.env['tlmp.transport.event'].search(domain, limit=50, order='planned_time')
        return {'count': len(events), 'records': events}

    def get_t1_overdue_summary(self):
        """Return dict with count + record list of overdue T1 documents.
        Rule: close_time IS NULL AND transport_order.t1_deadline < now"""
        # Search orders with t1_ref but no MRN close, and t1_deadline overdue
        domain = [
            ('t1_ref', '!=', False),
            ('t1_deadline', '<', fields.Datetime.to_string(datetime.now())),
        ]
        orders = self.env['tlmp.transport.order'].search(domain, limit=50, order='t1_deadline')
        return {'count': len(orders), 'records': orders}

    def get_exception_overdue_summary(self):
        """Return dict with count + record list of overdue exceptions.
        Rule: exception_state in (open,processing) AND now - create_date > timeout_hours"""
        cutoff = datetime.now()
        exceptions = self.env['tlmp.transport.exception'].search([
            ('exception_state', 'in', ('open', 'processing')),
        ], limit=100)
        overdue = exceptions.filtered(
            lambda e: e.create_date and (cutoff - e.create_date).total_seconds() > (e.timeout_hours or 24) * 3600
        )
        return {'count': len(overdue), 'records': overdue}


class TransportDashboard(models.TransientModel):
    _name = 'tlmp.transport.dashboard'
    _description = 'Transport Operation Dashboard'

    event_timeout_count = fields.Integer(string='Event Overdue', compute='_compute_stats')
    t1_overdue_count = fields.Integer(string='T1 Overdue', compute='_compute_stats')
    exception_overdue_count = fields.Integer(string='Exception Overdue', compute='_compute_stats')

    def _compute_stats(self):
        svc = self.env['tlmp.transport.dashboard.service']
        self.event_timeout_count = svc.get_event_timeout_summary()['count']
        self.t1_overdue_count = svc.get_t1_overdue_summary()['count']
        self.exception_overdue_count = svc.get_exception_overdue_summary()['count']

    def action_event_timeout_list(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Overdue Events',
            'res_model': 'tlmp.transport.event',
            'view_mode': 'list,form',
            'domain': [
                ('event_state', 'not in', ('completed', 'cancelled', 'skipped')),
                ('planned_time', '<', fields.Datetime.to_string(datetime.now())),
            ],
        }

    def action_t1_overdue_list(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'T1 Overdue Orders',
            'res_model': 'tlmp.transport.order',
            'view_mode': 'list,form',
            'domain': [
                ('t1_ref', '!=', False),
                ('t1_deadline', '<', fields.Datetime.to_string(datetime.now())),
            ],
        }

    def action_exception_overdue_list(self):
        cutoff = fields.Datetime.to_string(datetime.now() - timedelta(hours=24))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Overdue Exceptions',
            'res_model': 'tlmp.transport.exception',
            'view_mode': 'list,form',
            'domain': [
                ('exception_state', 'in', ('open', 'processing')),
                ('create_date', '<', cutoff),
            ],
        }
