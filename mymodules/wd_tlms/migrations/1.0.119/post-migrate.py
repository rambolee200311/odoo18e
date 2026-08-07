# -*- coding: utf-8 -*-
"""Sprint49-B review fixes.

- Deactivate legacy RULE-VEHICLE config rows that matched every request.
- Recompute stored vehicle requirement results for existing requests.
- Backfill vehicle requirement snapshots for existing confirmed requests.
"""

import json

from odoo import SUPERUSER_ID, api

from odoo.addons.wd_tlms.business_matrix.rules.vehicle_rules import (
    check_vehicle_rules,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['tlmp.business.rule'].sudo().search([
        ('code', 'like', 'RULE-VEHICLE-%'),
    ]).write({'active': False})

    requests = env['tlmp.transport.request'].sudo().with_context(
        skip_vehicle_requirement_validation=True)
    for request in requests.search([]):
        request._compute_vehicle_requirement_mode()
        context = request._vehicle_requirement_context({}, record=request)
        violations = check_vehicle_rules(context)
        result = ('block' if any(v.get('result') == 'block' for v in violations)
                  else 'warning' if violations else 'pass')
        request.write({
            'vehicle_requirement_validation_result': result,
            'vehicle_requirement_validation_violations': json.dumps(
                violations, ensure_ascii=False),
        })
        if request.state == 'confirmed' and not request.vehicle_requirement_mode_snapshot:
            request.write({
                'vehicle_requirement_mode_snapshot': request.vehicle_requirement_mode,
            })
            request.write({
                'vehicle_requirement_snapshot': request._build_vehicle_requirement_snapshot(),
                'vehicle_requirement_snapshot_status': 'frozen',
            })
    requests.flush_model()
