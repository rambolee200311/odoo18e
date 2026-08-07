"""Matching exception handler — detects match failures and low confidence."""
import json
from datetime import datetime
from odoo import api, fields, models


class MatchingExceptionHandler(models.AbstractModel):
    _name = 'tlmp.exception.handler.matching'
    _description = 'Matching Exception Handler'
    _inherit = 'tlmp.exception.handler.base'

    @api.model
    def get_supported_types(self):
        return ['MATCH_FAILED']

    @api.model
    def detect(self, source_record):
        suggestions = source_record.suggestion_ids.filtered(
            lambda s: s.state == 'draft' and s.confidence_score < 0.7)
        results = []
        for sug in suggestions:
            results.append({
                'exception_type': 'MATCH_FAILED',
                'priority': 'high' if sug.confidence_score < 0.5 else 'normal',
                'description': 'Match failed: confidence=%.2f, rule=%s' % (
                    sug.confidence_score, sug.match_rule_id.name or ''),
                'snapshot': {
                    'confidence_score': sug.confidence_score,
                    'confidence_source': sug.confidence_source,
                    'rule_id': sug.match_rule_id.id,
                    'rule_name': sug.match_rule_id.name,
                },
            })
        return results
