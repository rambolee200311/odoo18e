"""Settlement Exception Detector — scans settlement domain for anomalies.

Architecture:
  Detector (orchestrator)
    → Handler Registry
      → MatchingHandler / BillingHandler / ImportHandler
        → Each handler returns list of detected exceptions
          → Detector creates tlmp.settlement.exception records

Sprint38: Rule Engine replaces registry with dynamic rules.
"""
import json
from datetime import datetime
from odoo import api, fields, models, _


class ExceptionDetector(models.AbstractModel):
    _name = 'tlmp.exception.detector'
    _description = 'Settlement Exception Detector'

    @api.model
    def scan_all(self):
        """Scan all settlement domain sources for exceptions.
        Sprint38: Rule Engine priority → Legacy Handler fallback."""
        results = []
        engine = self.env['tlmp.rule.engine']
        # Scan import batches, billing documents, suggestions
        for batch in self.env['tlmp.carrier.invoice.import'].search([('state', '=', 'partial_failed')]):
            result = engine.scan('tlmp.carrier.invoice.import', batch.id, {
                'source_model': 'tlmp.carrier.invoice.import', 'source_res_id': batch.id,
                'source_display_name': batch.name,
            })
            results.append(result)
        for doc in self.env['tlmp.carrier.billing.document'].search([('state', '=', 'active')]):
            result = engine.scan('tlmp.carrier.billing.document', doc.id, {
                'source_model': 'tlmp.carrier.billing.document', 'source_res_id': doc.id,
                'source_display_name': doc.name,
                'billing_amount': doc.total_amount,
            })
            results.append(result)
        for sug in self.env['tlmp.carrier.match.suggestion'].search([('state', '=', 'draft'), ('confidence_score', '<', 0.7)]):
            result = engine.scan('tlmp.carrier.match.suggestion', sug.id, {
                'source_model': 'tlmp.carrier.match.suggestion', 'source_res_id': sug.id,
                'matching_confidence': sug.confidence_score,
            })
            results.append(result)
        return results

    @api.model
    def _scan_source(self, handler):
        """Run a specific handler against all relevant source records."""
        results = []
        supported = handler.get_supported_types()

        if 'MATCH_FAILED' in supported:
            suggestions = self.env['tlmp.carrier.match.suggestion'].search([
                ('state', '=', 'draft'),
                ('confidence_score', '<', 0.7),
            ])
            for sug in suggestions:
                results += handler.detect(sug)

        if 'AMOUNT_MISMATCH' in supported:
            docs = self.env['tlmp.carrier.billing.document'].search([
                ('state', '=', 'active'),
            ])
            for doc in docs:
                results += handler.detect(doc)

        if 'IMPORT_ERROR' in supported:
            batches = self.env['tlmp.carrier.invoice.import'].search([
                ('state', '=', 'partial_failed'),
            ])
            for batch in batches:
                results += handler.detect(batch)

        return results

    @api.model
    def create_exception(self, detection_result, source_record):
        """Create a tlmp.settlement.exception from a detection result."""
        snapshot = detection_result.get('snapshot', {})
        exception_type = detection_result.get('exception_type')

        # Check business idempotency — don't create duplicate exceptions
        existing = self.env['tlmp.settlement.exception'].search([
            ('exception_type', '=', exception_type),
            ('source_model', '=', source_record._name),
            ('source_res_id', '=', source_record.id),
            ('state', 'not in', ('closed', 'cancelled')),
        ], limit=1)
        if existing:
            return existing

        priority = detection_result.get('priority', 'normal')
        description = detection_result.get('description', '')

        exception = self.env['tlmp.settlement.exception'].create({
            'creation_method': 'legacy_handler',
            'exception_type': exception_type,
            'priority': priority,
            'description': description,
            'source_model': source_record._name,
            'source_res_id': source_record.id,
            'source_display_name': source_record.display_name or str(source_record.id),
            'source_snapshot': json.dumps(snapshot, default=str),
            'source_captured_at': fields.Datetime.now(),
        })

        # Auto-resolve if handler supports it
        registry = self.env['tlmp.exception.handler.registry']
        handler = registry.get_handler(exception_type)
        if handler and handler.auto_resolve(exception):
            exception.action_auto_resolve()

        return exception
