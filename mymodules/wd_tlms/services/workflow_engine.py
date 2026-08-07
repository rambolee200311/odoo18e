# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WorkflowEngine(models.AbstractModel):
    """Shared transition service: guard -> ledger -> state write."""

    _name = 'tlmp.workflow.engine'
    _description = 'TLMS Workflow Engine'

    def write_event(self, record, event_type, event_category='state',
                    from_state=False, to_state=False, payload=None,
                    source='manual'):
        code = self.env['tlmp.transport.event.code'].sudo().search([
            ('code', '=', event_type),
            ('active', '=', True),
        ], limit=1)
        if not code:
            raise UserError(_(
                'Event code %s is not in the transport event dictionary.') %
                event_type)
        if code.deprecated_at:
            _logger.warning(
                'Using deprecated transport event code %s.', code.code)
        self.env['tlmp.transport.event.ledger'].create({
            'res_model': record._name,
            'res_id': record.id,
            'event_code_id': code.id,
            'event_type': code.code,
            'event_code_status': 'validated',
            'event_category': event_category,
            'from_state': from_state or False,
            'to_state': to_state or False,
            'payload': payload,
            'source': source,
        })
        return True

    def _get_guard_rule(self, record, to_state):
        model = record._name
        from_state = record.state if 'state' in record._fields else False
        Guard = self.env['tlmp.workflow.guard'].sudo()
        rule = Guard.search([
            ('res_model', '=', model),
            ('from_state', '=', from_state or '*'),
            ('to_state', '=', to_state),
            ('active', '=', True),
        ], limit=1)
        if not rule:
            rule = Guard.search([
                ('res_model', '=', model),
                ('from_state', '=', '*'),
                ('to_state', '=', '*'),
                ('active', '=', True),
            ], limit=1)
        return rule

    def _check_guard(self, rule, record):
        code = rule.guard_code
        if code == 'general':
            return None
        if code == 'validation_state_passed':
            return (_('Validation state must be passed before processing.')
                    if record.validation_state != 'passed' else None)
        if code == 'quote_customer_approval':
            return (_('Customer acceptance is required for quote confirmation.')
                    if not record.customer_accept else None)
        if code in ('pod_received', 'delivery_completed'):
            event_type = 'POD_RECEIVED' if code == 'pod_received' \
                else 'DELIVERY_COMPLETED'
            exists = self.env['tlmp.transport.event.ledger'].sudo().search_count([
                ('res_model', '=', record._name),
                ('res_id', '=', record.id),
                ('event_type', '=', event_type),
            ])
            return (_('Required event %s is missing.') % event_type
                    if not exists else None)
        if code == 'assignment_context_required':
            context = getattr(record, 'assignment_context', False)
            req = (record.transport_request_id
                   if 'transport_request_id' in record._fields else False)
            if req and req.vehicle_requirement_mode_snapshot == 'exempted':
                return None
            return (_('Assignment context is required before resource reservation.')
                    if not context else None)
        return (_('Unknown workflow guard code: %s.') % code)

    def transition(self, record, to_state, event_type, event_category='state',
                   guard=None, payload=None, extra_vals=None, source='manual'):
        record.ensure_one()
        if guard:
            guard_error = guard(record)
            if guard_error:
                raise UserError(guard_error)
        rule = self._get_guard_rule(record, to_state)
        if not rule:
            from_state = record.state if 'state' in record._fields else False
            raise UserError(_(
                'No workflow guard configured for %s: %s -> %s (default BLOCK).'
            ) % (record._name, from_state, to_state))
        guard_error = self._check_guard(rule, record)
        if guard_error:
            raise UserError(guard_error)
        from_state = record.state if 'state' in record._fields else False
        self.write_event(
            record, event_type, event_category,
            from_state=from_state, to_state=to_state, payload=payload,
            source=source)
        vals = {'state': to_state}
        if extra_vals:
            vals.update(extra_vals)
        record.write(vals)
        return True
