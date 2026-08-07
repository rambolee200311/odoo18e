"""Import exception handler — detects import errors."""
from odoo import api, models


class ImportExceptionHandler(models.AbstractModel):
    _name = 'tlmp.exception.handler.import'
    _description = 'Import Exception Handler'
    _inherit = 'tlmp.exception.handler.base'

    @api.model
    def get_supported_types(self):
        return ['IMPORT_ERROR']

    @api.model
    def detect(self, source_record):
        results = []
        if hasattr(source_record, 'state') and source_record.state == 'partial_failed':
            for line in source_record.line_ids.filtered(lambda l: l.import_status == 'failed'):
                results.append({
                    'exception_type': 'IMPORT_ERROR',
                    'priority': 'normal',
                    'description': 'Import line %d failed: %s' % (
                        line.line_no, line.validation_error_message or 'Unknown error'),
                    'snapshot': {
                        'import_batch_id': source_record.id,
                        'line_no': line.line_no,
                        'error_code': line.validation_error_code,
                        'error_message': line.validation_error_message,
                    },
                })
        return results
