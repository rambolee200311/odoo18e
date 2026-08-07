from odoo import api, fields, models, _


class TransportMatchService(models.AbstractModel):
    """Transport Match Service — 匹配建议服务
    基于 transport.reference 和 match.rule 生成匹配建议。
    一期仅支持 reference.ref_type + reference.ref_value 匹配。
    """
    _name = 'tlmp.transport.match.service'
    _description = 'Transport Match Service'

    @api.model
    def suggest_matches(self, billing_line, rules=None):
        """为 billing.line 生成匹配建议
        :param billing_line: billing.line record (browse)
        :param rules: optional rule filter, defaults to active rules
        :return: list of suggestion dicts (not yet created as records)
        """
        if not billing_line:
            return []

        if rules is None:
            rules = self.env['tlmp.carrier.match.rule'].search([
                ('is_active', '=', True)
            ], order='sequence, id')

        suggestions = []
        for rule in rules:
            # Query transport.reference by rule conditions
            domain = [('ref_type', '=', rule.match_ref_type),
                      ('ref_value', '=', rule.match_ref_value),
                      ('active', '=', True)]
            references = self.env['tlmp.transport.reference'].search(domain)

            for ref in references:
                if ref.res_model == 'tlmp.transport.order' and ref.res_id:
                    order = self.env['tlmp.transport.order'].browse(ref.res_id)
                    if order.exists():
                        suggestions.append({
                            'billing_line_id': billing_line.id,
                            'candidate_reference': order.id,
                            'candidate_reference_model': 'tlmp.transport.order',
                            'match_rule_id': rule.id,
                            'confidence_score': self._compute_confidence(rule, ref, billing_line),
                            'confidence_source': 'rule_match',
                            'state': 'draft',
                        })
        return suggestions

    @api.model
    def _compute_confidence(self, rule, reference, billing_line):
        """Compute confidence score for a match suggestion.
        Base score: rule.sequence / match type (BL exact > container exact > tracking)
        """
        base_scores = {
            'bl_no': 0.95,
            'container_no': 0.85,
            'tracking_no': 0.80,
            'cmr_no': 0.90,
            'pickup_code': 0.75,
            'shipment_no': 0.85,
            'booking_no': 0.70,
            'po_no': 0.65,
            'delivery_no': 0.70,
        }
        return base_scores.get(rule.match_ref_type, 0.5)

    @api.model
    def create_suggestion(self, suggestion_data):
        """Create a match.suggestion record and log history."""
        candidate_ref = '%s,%d' % (
            suggestion_data.get('candidate_reference_model'),
            suggestion_data.get('candidate_reference'))
        suggestion = self.env['tlmp.carrier.match.suggestion'].create({
            'billing_line_id': suggestion_data['billing_line_id'],
            'candidate_reference': candidate_ref,
            'match_rule_id': suggestion_data.get('match_rule_id'),
            'confidence_score': suggestion_data.get('confidence_score', 0.0),
            'confidence_source': suggestion_data.get('confidence_source', 'rule_match'),
        })
        self.env['tlmp.carrier.matching.history'].create({
            'billing_line_id': suggestion.billing_line_id.id,
            'transport_order_id': suggestion.candidate_order_id.id if suggestion.candidate_order_id else False,
            'match_rule_id': suggestion.match_rule_id.id if suggestion.match_rule_id else False,
            'suggestion_id': suggestion.id,
            'operation': 'suggestion_created',
            'from_state': False,
            'to_state': 'draft',
            'operator': self.env.uid,
        })
        return suggestion
