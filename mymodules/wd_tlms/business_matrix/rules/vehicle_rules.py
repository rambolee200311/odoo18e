"""RULE-VEHICLE-000~005 static handlers (executed by Business Matrix Rule Engine).

Sprint49-B canonical rule IDs (INT-TMS-SPRINT49B-001):
  RULE-VEHICLE-000 - mode split (exempted skips every vehicle check)
  RULE-VEHICLE-001 - service type split via carrier_type_vehicle_policy
  RULE-VEHICLE-002 - dangerous goods: ADR carrier capability, ADR vehicle
                     capability, DG / normal fleet mutual exclusion
  RULE-VEHICLE-003 - vehicle capacity requirement
  RULE-VEHICLE-005 - vehicle body type matching
"""

from datetime import date


CAPACITY_RULES = {
    'below_40t': ('< 40t', lambda capacity: capacity < 40),
    '40t_44t': ('40t-44t', lambda capacity: 40 <= capacity <= 44),
    'over_44t': ('> 44t', lambda capacity: capacity > 44),
}


def _append(violations, rule_id, message, result):
    violations.append({
        'rule_id': rule_id,
        'message': message,
        'result': result,
    })


def check_vehicle_rules(ctx):
    """Execute vehicle requirement rules against the given context.
    Returns a list of violation dicts (PASS when empty).

    Priority chain: Service Type Split > ADR Compliance > Capacity > Body Type.
    Capacity/body constraints are soft (WARNING) at request stage; they become
    BLOCK when an assigned vehicle is provided and does not satisfy them.
    """
    violations = []
    vehicle_mode = ctx.get('vehicle_requirement_mode', 'required')

    # RULE-VEHICLE-000 / RULE-VEHICLE-001: service type split
    if vehicle_mode == 'exempted':
        return violations  # skip all vehicle checks for exempted mode

    carrier = ctx.get('carrier_type')
    carrier_caps = ctx.get('carrier_capabilities') or set()
    vehicle_body = ctx.get('vehicle_body_type')
    vehicle_cap = ctx.get('vehicle_capacity_requirement')
    is_dg = ctx.get('is_dangerous_goods', 'normal')

    # RULE-VEHICLE-002: dangerous goods compliance chain
    if is_dg == 'adr_dangerous':
        if carrier == 'courier':
            _append(violations, 'RULE-VEHICLE-002',
                    '快递承运商禁止承运ADR危险品', 'block')
        if 'adr' not in carrier_caps:
            _append(violations, 'RULE-VEHICLE-002',
                    'ADR危险品运输需承运商持有ADR资质', 'block')
        assigned_adr = ctx.get('assigned_vehicle_adr')
        if assigned_adr is not None and not assigned_adr:
            _append(violations, 'RULE-VEHICLE-002',
                    '分配车辆未持有ADR认证', 'block')
        if not (ctx.get('dg_adr_class') and ctx.get('dg_un_code')):
            _append(violations, 'RULE-VEHICLE-002',
                    'ADR危险品需求必须填写ADR Class和UN Code', 'block')

    # RULE-VEHICLE-004: ADR driver qualification (Sprint50-A)
    driver_adr_valid = ctx.get('driver_adr_valid')
    driver_expiry = ctx.get('driver_adr_expiry_date')
    driver_id = ctx.get('driver_id')
    if is_dg == 'adr_dangerous':
        if driver_adr_valid is not None and not driver_adr_valid:
            _append(violations, 'RULE-VEHICLE-004',
                    '分配司机未持有有效ADR从业资质', 'block')
        if driver_expiry:
            try:
                expired = date.fromisoformat(str(driver_expiry)) < date.today()
            except (TypeError, ValueError):
                expired = True
            if expired:
                _append(violations, 'RULE-VEHICLE-004',
                        '分配司机ADR从业资质已过期', 'block')
        if ctx.get('assignment_context_required') and not (
                driver_adr_valid or driver_expiry or driver_id):
            _append(violations, 'RULE-VEHICLE-004',
                    '未提供司机ADR资质上下文（assignment_context）', 'block')

    # RULE-VEHICLE-003: vehicle capacity requirement
    if vehicle_cap and vehicle_cap != 'no_limit':
        label, satisfies = CAPACITY_RULES[vehicle_cap]
        assigned_capacity = ctx.get('assigned_vehicle_capacity')
        if assigned_capacity is not None:
            if not satisfies(assigned_capacity):
                _append(violations, 'RULE-VEHICLE-003',
                        '车辆额定载重不满足运输需求下限：%s' % label, 'block')
        else:
            _append(violations, 'RULE-VEHICLE-003',
                    '车辆载重下限需求：%s' % label, 'warning')

    # RULE-VEHICLE-005: vehicle body type matching
    if vehicle_body and vehicle_body != 'no_requirement':
        assigned_body = ctx.get('assigned_vehicle_body_type')
        if assigned_body:
            if assigned_body != vehicle_body:
                _append(violations, 'RULE-VEHICLE-005',
                        '车辆装卸类型不满足运输需求：%s' % assigned_body, 'block')
        else:
            _append(violations, 'RULE-VEHICLE-005',
                    '车辆装卸类型需求：%s' % vehicle_body, 'warning')

    return violations
