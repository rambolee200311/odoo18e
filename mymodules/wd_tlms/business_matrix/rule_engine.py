from datetime import datetime

from .rule_definition import RESULT_BLOCK, RESULT_WARNING, RESULT_PASS
from .rules import cargo_rules, carrier_rules, compliance_rules, vehicle_rules


class BusinessMatrixEngine:
    """Executes configured tlmp.business.rule records; falls back to static handlers."""

    @staticmethod
    def validate(env, dimensions):
        rules = env['tlmp.business.rule'].sudo().search(
            [('active', '=', True)], order='priority')
        violations = []
        if rules:
            for rule in rules:
                # carrier_type_vehicle_policy rows only configure applicability;
                # they must not be treated as matrix violations.
                if rule.vehicle_policy_mode:
                    continue
                if BusinessMatrixEngine._rule_matches(rule, dimensions):
                    violations.append({
                        'rule_id': rule.code,
                        'message': rule.message_cn,
                        'result': rule.result,
                        'timestamp': datetime.utcnow().isoformat(),
                    })
        else:
            violations += cargo_rules.check_cargo_rules(dimensions)
            violations += carrier_rules.check_carrier_rules(dimensions)
            violations += compliance_rules.check_compliance_rules(dimensions)
        # Static vehicle handlers stay active even when configured matrix
        # rules exist (Sprint49-B request-stage vehicle requirement rules).
        violations += vehicle_rules.check_vehicle_rules(dimensions)
        for violation in violations:
            violation.setdefault('timestamp', datetime.utcnow().isoformat())
        if violations:
            result = RESULT_BLOCK if any(
                v.get('result') == 'block' for v in violations) else RESULT_WARNING
        else:
            result = RESULT_PASS
        return {'result': result, 'violations': violations}

    @staticmethod
    def _rule_matches(rule, dim):
        if rule.require_capability:
            capabilities = set(dim.get('carrier_capabilities') or [])
            if rule.require_capability in capabilities:
                return False
        if rule.apply_mixed_root and not dim.get('mixed_roots'):
            return False
        if rule.cargo_category and dim.get('cargo_category') != rule.cargo_category:
            return False
        if rule.carrier_type and dim.get('carrier_type') != rule.carrier_type:
            return False
        if rule.t1_attribute and dim.get('t1_attribute') != rule.t1_attribute:
            return False
        if rule.dg_attribute and dim.get('dg_attribute') != rule.dg_attribute:
            return False
        return True
