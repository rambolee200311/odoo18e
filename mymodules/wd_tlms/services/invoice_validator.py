import json, hashlib
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InvoiceValidator(models.AbstractModel):
    _name = 'tlmp.invoice.validator'
    _description = 'Invoice Validator — Business Idempotency + Technical Hash + Field Transformation'

    @api.model
    def compute_idempotency_hash(self, carrier_id, external_invoice_no, invoice_version, file_checksum=''):
        """SHA256 technical_duplicate_detection_hash."""
        raw = '%s|%s|%s|%s' % (str(carrier_id), str(external_invoice_no),
                                str(invoice_version), str(file_checksum))
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    @api.model
    def check_business_idempotency(self, carrier_id, external_invoice_no, invoice_version):
        """Check if same business key already exists (non-superseded)."""
        domain = [
            ('carrier_id', '=', carrier_id),
            ('external_invoice_no', '=', external_invoice_no),
            ('invoice_version', '=', invoice_version),
            ('state', 'in', ('draft', 'active')),
        ]
        existing = self.env['tlmp.carrier.billing.document'].search(domain)
        if existing:
            return {'duplicate': True, 'existing_document': existing[:1].id,
                    'message': 'Invoice %s v%s already exists (state=%s)' % (
                        external_invoice_no, invoice_version, existing[:1].state)}
        return {'duplicate': False}

    @api.model
    def check_technical_duplicate(self, idempotency_hash):
        """Check if same file hash already imported (any state)."""
        existing = self.env['tlmp.carrier.billing.document'].search([
            ('idempotency_hash', '=', idempotency_hash)], limit=1)
        if existing:
            return {'duplicate': True, 'existing_document': existing.id}
        return {'duplicate': False}

    @api.model
    def check_line_idempotency(self, document_ids, external_line_key):
        """Check if a line with same key exists within given documents."""
        if not external_line_key or not document_ids:
            return {'duplicate': False}
        existing = self.env['tlmp.carrier.billing.line'].search([
            ('document_id', 'in', document_ids),
            ('external_line_key', '=', external_line_key)], limit=1)
        if existing:
            return {'duplicate': True, 'existing_line': existing.id}
        return {'duplicate': False}

    @api.model
    def apply_mapping(self, row_data, template):
        """Transform a CSV/XLSX row array into a dict of billing field values using template mapping."""
        mapping = template.mapping_json
        try:
            rules = json.loads(mapping)
        except (json.JSONDecodeError, TypeError):
            raise ValidationError(_('Template mapping JSON is invalid'))

        if isinstance(rules, dict):
            rules = [rules]

        result = {}
        for rule in rules:
            col_name = rule.get('source_column', '')
            target_field = rule.get('target_field', '')
            transform = rule.get('transform', 'char')

            # Find column index by header name
            raw_value = ''
            if isinstance(row_data, dict):
                raw_value = row_data.get(col_name, '')
            elif isinstance(row_data, (list, tuple)):
                raw_value = str(row_data[0]) if row_data else ''

            # Apply transform
            if transform == 'char':
                parsed = str(raw_value)
            elif transform == 'decimal':
                try:
                    parsed = float(str(raw_value).replace(',', '').replace(' ', ''))
                except (ValueError, TypeError):
                    parsed = 0.0
            elif transform == 'integer':
                try:
                    parsed = int(float(str(raw_value).replace(',', '')))
                except (ValueError, TypeError):
                    parsed = 0
            elif transform == 'date':
                parsed = str(raw_value)[:10] if raw_value else False
            elif transform == 'datetime':
                parsed = str(raw_value)[:19] if raw_value else False
            elif transform == 'boolean':
                parsed = str(raw_value).strip().lower() in ('true', '1', 'yes', 'y')
            elif transform == 'currency':
                try:
                    parsed = float(str(raw_value).replace(',', '').replace(' ', '').replace('$', '').replace(u'\u00a3', ''))
                except (ValueError, TypeError):
                    parsed = 0.0
            else:
                parsed = str(raw_value)

            result[target_field] = parsed

        return result

    @api.model
    def validate_row(self, parsed, template):
        """Validate parsed row data, return list of (error_code, error_message)."""
        errors = []
        if not isinstance(parsed, dict):
            errors.append(('INVALID_PARSED', 'Parsed data is not a dict'))
            return errors

        # Must have at least external_invoice_no or document_no
        if not parsed.get('external_invoice_no') and not parsed.get('document_no'):
            errors.append(('MISSING_IDENTITY', 'Row missing both external_invoice_no and document_no'))

        # Validate amount fields
        for fld in ('net_amount', 'tax', 'line_total'):
            val = parsed.get(fld, 0)
            if isinstance(val, (int, float)) and val < 0:
                errors.append(('NEGATIVE_AMOUNT', 'Field %s has negative value: %s' % (fld, val)))

        # Validate dates
        for fld in ('service_date', 'billing_period_start', 'billing_period_end'):
            val = parsed.get(fld)
            if val and len(str(val)) > 10:
                errors.append(('INVALID_DATE', 'Field %s has invalid date format: %s' % (fld, val)))

        return errors
