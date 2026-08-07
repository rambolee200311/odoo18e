"""RULE-CARRIER-001/002 static handlers."""


def check_carrier_rules(ctx):
    violations = []
    t1 = ctx.get('t1_attribute')
    dg = ctx.get('dg_attribute')
    capabilities = set(ctx.get('carrier_capabilities') or [])
    if t1 == 't1' and 't1' not in capabilities:
        violations.append({
            'rule_id': 'RULE-CARRIER-001',
            'message': '承运商缺少T1资质',
            'result': 'block',
        })
    if dg == 'dg' and 'dg' not in capabilities:
        violations.append({
            'rule_id': 'RULE-CARRIER-002',
            'message': '承运商缺少危险品资质',
            'result': 'block',
        })
    return violations
