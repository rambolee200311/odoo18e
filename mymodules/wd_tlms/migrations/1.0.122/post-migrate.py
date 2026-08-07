# -*- coding: utf-8 -*-
"""Sprint50-B: event code binding + TransportPlan state ownership backfill."""

from odoo import SUPERUSER_ID, api


KNOWN_CODES = {
    'REQUEST_CONFIRMED', 'REQUEST_SUBMITTED', 'REQUEST_PROCESSING',
    'REQUEST_COMPLETED', 'REQUEST_CANCELLED',
    'INQUIRY_SENT', 'INQUIRY_RESPONDED', 'INQUIRY_ACCEPTED',
    'INQUIRY_CLOSED', 'INQUIRY_REJECTED', 'INQUIRY_REOPENED',
    'QUOTE_SENT', 'QUOTE_ISSUED', 'QUOTE_APPROVED', 'QUOTE_CONFIRMED',
    'QUOTE_ACCEPTED', 'QUOTE_REJECTED', 'QUOTE_CANCELLED', 'QUOTE_EXPIRED',
    'ORDER_CONFIRMED', 'ORDER_ASSIGNED', 'ORDER_ALLOCATED',
    'ORDER_IN_TRANSIT', 'ORDER_EXCEPTION', 'ORDER_EXCEPTION_RECOVERED',
    'ORDER_DELIVERED', 'ORDER_POD_CONFIRMED', 'ORDER_BILLED',
    'ORDER_SETTLEMENT_PENDING', 'ORDER_SETTLED', 'ORDER_CLOSED',
    'ORDER_REOPENED', 'ORDER_CANCELLED',
    'PLAN_SCHEDULED', 'PLAN_RESERVED', 'PLAN_EXECUTING', 'PLAN_FINISHED',
    'PLAN_FAILED', 'PLAN_CANCELLED', 'POD_RECEIVED', 'DELIVERY_COMPLETED',
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    EventCode = env['tlmp.transport.event.code'].sudo()
    cr.execute(
        "SELECT DISTINCT event_type FROM tlmp_transport_event_ledger "
        "WHERE event_type IS NOT NULL AND event_code_id IS NULL")
    for (raw,) in cr.fetchall():
        code = raw if raw in KNOWN_CODES else 'LEGACY_%s' % raw
        existing = EventCode.search([('code', '=', code)], limit=1)
        if not existing:
            existing = EventCode.create({
                'code': code,
                'name': code,
                'category': 'business',
            })
        status = 'validated' if raw in KNOWN_CODES else 'legacy'
        cr.execute(
            "UPDATE tlmp_transport_event_ledger "
            "SET event_code_id=%s, event_code_status=%s, event_type=%s "
            "WHERE event_type=%s AND event_code_id IS NULL",
            (existing.id, status, code, raw))

    TransportPlan = env['tlmp.transport.plan'].sudo()
    cr.execute(
        "SELECT id, state, reservation_type, assignment_context, "
        "transport_request_id, name FROM pickup_plan "
        "WHERE transport_plan_id IS NULL")
    for pid, state, rtype, actx, req_id, name in cr.fetchall():
        mapped = {'confirmed': 'reserved', 'completed': 'finished'}.get(
            state, state if state in (
                'draft', 'scheduled', 'reserved', 'executing',
                'finished', 'failed', 'cancelled') else 'draft')
        abstract = TransportPlan.create({
            'name': name or 'PUP-%s' % pid,
            'plan_type': 'pickup',
            'state': mapped,
            'reservation_type': rtype or 'vehicle',
            'assignment_context': actx,
            'transport_request_id': req_id,
        })
        cr.execute(
            "UPDATE pickup_plan SET transport_plan_id=%s WHERE id=%s",
            (abstract.id, pid))

    cr.execute(
        "SELECT id, state, reservation_type, assignment_context, "
        "container_no FROM container_transport_plan "
        "WHERE transport_plan_id IS NULL")
    for pid, state, rtype, actx, container_no in cr.fetchall():
        mapped = {'confirmed': 'reserved', 'completed': 'finished'}.get(
            state, state if state in (
                'draft', 'scheduled', 'reserved', 'executing',
                'finished', 'failed', 'cancelled') else 'draft')
        abstract = TransportPlan.create({
            'name': 'CT-%s' % (container_no or pid),
            'plan_type': 'container',
            'state': mapped,
            'reservation_type': rtype or 'vehicle',
            'assignment_context': actx,
        })
        cr.execute(
            "UPDATE container_transport_plan "
            "SET transport_plan_id=%s WHERE id=%s",
            (abstract.id, pid))
