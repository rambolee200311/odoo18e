# -*- coding: utf-8 -*-
import json
import logging
from datetime import date, timedelta

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class PickupScheduleController(http.Controller):
    """Schedule calendar page and API endpoints for pickup plan scheduling.

    Provides:
    - GET  /pickup_schedule            - Calendar page (QWeb)
    - GET  /pickup_schedule/api/schedules  - Get scheduled plans for a month
    - POST /pickup_schedule/api/schedule   - Set schedule date for a plan
    - POST /pickup_schedule/api/unschedule - Clear schedule date for a plan
    """

    @http.route('/pickup_schedule', type='http', auth='user', website=False)
    def pickup_schedule_page(self, **kwargs):
        """Render the schedule calendar page."""
        return request.render('wd_tlms.pickup_schedule_template')

    @http.route('/pickup_schedule/api/schedules', type='http', auth='user',
                methods=['GET'], csrf=False)
    def api_get_schedules(self, year=None, month=None, **kwargs):
        """Return scheduled plans for the given month as JSON.

        Filters:
        - destination_id: optional warehouse filter
        - Only container-type plans are returned (pallet plans use container_line_ids).
        """
        PickupPlan = request.env['pickup.plan']
        now = date.today()
        year_int = int(year) if year else now.year
        month_int = int(month) if month else now.month

        start_str = f'{year_int}-{month_int:02d}-01'
        if month_int == 12:
            end_str = f'{year_int + 1}-01-01'
        else:
            end_str = f'{year_int}-{month_int + 1:02d}-01'

        domain = [
            ('scheduled_date', '>=', start_str),
            ('scheduled_date', '<', end_str),
        ]
        destination_filter = kwargs.get('destination_id')
        if destination_filter:
            domain.append(('warehouse_id', '=', int(destination_filter)))

        plans = PickupPlan.search(domain)
        result = {}
        for p in plans:
            ds = str(p.scheduled_date)
            if ds not in result:
                result[ds] = {'count': 0, 'plans': []}

            plan_data = {
                'plan_id': p.id,
                'scheduled_date': ds,
                'name': p.name,
                'cargo_type': p.cargo_type,
                'pallet_count': p.pallet_count,
                'cargo_weight': p.cargo_weight,
                'cargo_description': p.cargo_description or '',
                'warehouse': p.warehouse_id.name if p.warehouse_id else '',
                'containers': [],
            }

            if p.cargo_type == 'container':
                for cl in p.container_line_ids:
                    plan_data['containers'].append({
                        'container_number': cl.container_number,
                        'container_type': cl.container_type,
                        'bl_number': cl.bl_number,
                        'weight': cl.weight,
                    })
                    result[ds]['count'] += 1
            else:
                # Pallet plan - count as 1 item
                result[ds]['count'] += 1

            result[ds]['plans'].append(plan_data)

        return request.make_response(
            json.dumps(result),
            headers=[('Content-Type', 'application/json')],
        )

    @http.route('/pickup_schedule/api/schedule', type='json', auth='user',
                methods=['POST'], csrf=False)
    def api_set_schedule(self, plan_id=None, scheduled_date=None, **kwargs):
        """Set schedule date for a pickup plan.

        Called from the calendar page when a container/pallet is dropped on a date.
        """
        if not plan_id or not scheduled_date:
            return {'ok': False, 'error': _('Missing plan_id or scheduled_date')}

        plan = request.env['pickup.plan'].browse(int(plan_id))
        if not plan.exists():
            return {'ok': False, 'error': _('Plan not found')}

        old_date = plan.scheduled_date
        plan.scheduled_date = scheduled_date

        # Count items on the new date
        month_start = scheduled_date[:8] + '01'
        next_month = int(scheduled_date[5:7])
        next_year = int(scheduled_date[:4])
        if next_month == 12:
            month_end = f'{next_year + 1}-01-01'
        else:
            month_end = f'{next_year}-{next_month + 1:02d}-01'

        day_count = request.env['pickup.plan'].search_count([
            ('scheduled_date', '=', scheduled_date),
        ])

        return {'ok': True, 'day_count': day_count, 'old_date': str(old_date) if old_date else None}

    @http.route('/pickup_schedule/api/unschedule', type='json', auth='user',
                methods=['POST'], csrf=False)
    def api_unschedule(self, plan_id=None, **kwargs):
        """Clear schedule date for a pickup plan.

        Called when a scheduled item is removed from the calendar.
        """
        if not plan_id:
            return {'ok': False, 'error': _('Missing plan_id')}

        plan = request.env['pickup.plan'].browse(int(plan_id))
        if not plan.exists():
            return {'ok': False, 'error': _('Plan not found')}

        removed_date = plan.scheduled_date
        plan.scheduled_date = False

        # Count remaining items on the removed date
        day_count = request.env['pickup.plan'].search_count([
            ('scheduled_date', '=', str(removed_date)),
        ]) if removed_date else 0

        return {'ok': True, 'day_count': day_count, 'removed_date': str(removed_date) if removed_date else None}

    @http.route('/pickup_schedule/api/unplanned', type='http', auth='user', csrf=False)
    def api_get_unplanned(self, destination_id=None, warehouse_id=None, **kwargs):
        """Return all unscheduled plans for the left-side panel.

        Filters:
        - destination_id (int): filter by warehouse id
        - warehouse_id (int): same as destination_id, kept for compatibility
        """
        domain = [('scheduled_date', '=', False)]
        dest_id = destination_id or warehouse_id
        if dest_id:
            domain.append(('warehouse_id', '=', int(dest_id)))

        plans = request.env['pickup.plan'].search_read(domain, [
            'id', 'name', 'cargo_type', 'cargo_description',
            'pallet_count', 'cargo_weight', 'warehouse_id',
            'container_line_ids',
        ])

        result = []
        for p in plans:
            item = {
                'plan_id': p['id'],
                'name': p['name'],
                'cargo_type': p['cargo_type'],
                'cargo_description': p['cargo_description'] or '',
                'pallet_count': p['pallet_count'] or 0,
                'cargo_weight': p['cargo_weight'] or 0,
                'warehouse': '',
                'containers': [],
            }
            if p['warehouse_id']:
                wh = request.env['stock.warehouse'].browse(p['warehouse_id'][0])
                item['warehouse'] = wh.name

            if p['cargo_type'] == 'container' and p['container_line_ids']:
                for cl_id in p['container_line_ids']:
                    cl = request.env['pickup.plan.container.line'].browse(cl_id)
                    item['containers'].append({
                        'id': cl.id,
                        'container_number': cl.container_number,
                        'container_type': cl.container_type,
                        'bl_number': cl.bl_number,
                        'weight': cl.weight,
                    })

            result.append(item)

        data = json.dumps(result)
        return request.make_response(data, headers=[('Content-Type', 'application/json')])


    # ================================================================
    # Sprint 2: schedule.plan.schedule API endpoints
    # These use the new schedule.plan.schedule model for 
    # proper state management and overlap prevention.
    # ================================================================

    @http.route('/pickup_schedule/api/v2/schedules', type='json', auth='user',
                methods=['GET'], csrf=False)
    def api_v2_get_schedules(self, year=None, month=None, destination_id=None, **kwargs):
        """Return scheduled plans for the given month (using schedule.plan.schedule model).
        
        Returns structured data for the calendar grid with overlap-safe scheduling.
        """
        Schedule = request.env['schedule.plan.schedule']
        return Schedule.api_get_schedules(year, month, destination_id)

    @http.route('/pickup_schedule/api/v2/unplanned', type='json', auth='user',
                methods=['GET'], csrf=False)
    def api_v2_get_unplanned(self, destination_id=None, warehouse_id=None, **kwargs):
        """Return unscheduled plans for the left-side panel.
        
        Uses schedule.plan.schedule model for enhanced filtering and 
        cargo-type-aware scheduling (containers vs pallets).
        """
        Schedule = request.env['schedule.plan.schedule']
        return Schedule.api_get_unplanned(destination_id, warehouse_id)

    @http.route('/pickup_schedule/api/v2/schedule', type='json', auth='user',
                methods=['POST'], csrf=False)
    def api_v2_set_schedule(self, plan_id=None, scheduled_date=None, container_line_id=None, **kwargs):
        """Create a schedule using schedule.plan.schedule model.
        
        Supports both container-level and plan-level scheduling.
        Prevents overlap via SQL unique constraint.
        """
        Schedule = request.env['schedule.plan.schedule']
        return Schedule.api_create_schedule(plan_id, scheduled_date, container_line_id)

    @http.route('/pickup_schedule/api/v2/unschedule', type='json', auth='user',
                methods=['POST'], csrf=False)
    def api_v2_unschedule(self, schedule_id=None, **kwargs):
        """Cancel a schedule record.
        
        Properly manages state transition and cleans up plan.scheduled_date.
        """
        if not schedule_id:
            return {'ok': False, 'error': _('Missing schedule_id')}
        Schedule = request.env['schedule.plan.schedule']
        return Schedule.api_delete_schedule(int(schedule_id))
