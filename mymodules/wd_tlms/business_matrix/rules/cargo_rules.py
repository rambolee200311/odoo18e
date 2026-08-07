"""RULE-CARGO-001~005 static handlers (used as fallback when no configured rules)."""


def check_cargo_rules(ctx):
    violations = []
    cargo = ctx.get('cargo_category')
    carrier = ctx.get('carrier_type')
    t1 = ctx.get('t1_attribute')
    dg = ctx.get('dg_attribute')
    if cargo == 'container' and carrier == 'courier':
        violations.append({
            'rule_id': 'RULE-CARGO-001',
            'message': '整柜运输不允许快递公司承运',
            'result': 'block',
        })
    if cargo == 'piece' and t1 == 't1':
        violations.append({
            'rule_id': 'RULE-CARGO-002',
            'message': '散件不承接T1跨境监管运输',
            'result': 'block',
        })
    if carrier == 'courier' and t1 == 't1':
        violations.append({
            'rule_id': 'RULE-CARGO-003',
            'message': '快递公司无跨境T1报关配套能力',
            'result': 'block',
        })
    if carrier == 'courier' and dg == 'dg':
        violations.append({
            'rule_id': 'RULE-CARGO-004',
            'message': '普通快递无危化运输资质',
            'result': 'block',
        })
    if ctx.get('mixed_roots'):
        violations.append({
            'rule_id': 'RULE-CARGO-005',
            'message': '单个运输需求禁止混合Cargo Category Root',
            'result': 'block',
        })
    return violations
