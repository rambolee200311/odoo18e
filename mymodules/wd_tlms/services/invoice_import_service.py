import json, base64
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InvoiceImportService(models.AbstractModel):
    """Invoice Import Orchestrator — Settlement Intake Layer main service.
    Flow: upload → parse → validate → preview → confirm → write (line-isolated)."""
    _name = 'tlmp.invoice.import.service'
    _description = 'Invoice Import Service — Intake Layer Orchestrator'

    @api.model
    def run_preview(self, import_batch):
        """Phase 1: Parse file + validate idempotency + write Import Lines (preview data only).
        Does NOT create billing documents."""
        batch = import_batch
        template = batch.template_id
        if not template:
            raise ValidationError(_('No template configured for this import batch.'))

        raw = batch.file_data
        if not raw:
            raise ValidationError(_('No file uploaded.'))

        try:
            raw_bytes = base64.b64decode(raw)
        except Exception:
            raise ValidationError(_('Invalid file data (base64 decode failed).'))

        # Parse
        Parser = self.env['tlmp.invoice.parser']
        enc = template.encoding
        if template.file_type == 'csv':
            rows, detected_enc = Parser.parse_csv(
                raw_bytes, encoding=enc, delimiter=template.delimiter)
        elif template.file_type == 'xlsx':
            rows = Parser.parse_xlsx(raw_bytes)
        else:
            raise ValidationError(_('Unsupported file type: %s') % template.file_type)

        # Skip header if needed
        data_rows = rows[1:] if template.has_header and rows else rows
        batch.write({'total_lines': len(data_rows), 'state': 'preview'})

        # Generate Import Lines for preview
        line_model = self.env['tlmp.carrier.invoice.import.line']
        existing_lines = batch.line_ids
        if existing_lines:
            existing_lines.unlink()

        for idx, row in enumerate(data_rows):
            parsed = self.env['tlmp.invoice.validator'].apply_mapping(row, template)
            raw_json = json.dumps(row) if isinstance(row, (list, tuple)) else json.dumps(row)
            parsed_json = json.dumps(parsed, default=str)

            line_model.create({
                'import_id': batch.id,
                'line_no': idx + 1,
                'raw_data': raw_json,
                'parsed_data': parsed_json,
                'import_status': 'parsed',
            })

        # Check business idempotency (via parsed data from first line)
        Validator = self.env['tlmp.invoice.validator']
        first_parsed = {}
        if data_rows:
            first_parsed = Validator.apply_mapping(data_rows[0], template)
        ext_no = first_parsed.get('external_invoice_no', '')
        ext_ver = first_parsed.get('invoice_version', '')
        idem_check = Validator.check_business_idempotency(
            batch.carrier_partner_id.id, ext_no, ext_ver)
        if idem_check.get('duplicate'):
            batch.write({'state': 'validated'})
        else:
            batch.write({'state': 'validated'})

        return {
            'status': 'ok',
            'total_lines': len(data_rows),
            'business_duplicate': idem_check.get('duplicate', False),
            'existing_document': idem_check.get('existing_document'),
        }

    @api.model
    def run_confirm_import(self, import_batch):
        """Phase 2: Confirm import — write billing documents from Import Lines.
        Line-isolated processing: each line is an independent unit."""
        batch = import_batch
        template = batch.template_id
        if not template:
            raise ValidationError(_('No template configured.'))

        Validator = self.env['tlmp.invoice.validator']
        Writer = self.env['tlmp.invoice.writer']

        lines = batch.line_ids.filtered(lambda l: l.import_status in ('parsed', 'validated'))
        success = 0
        errors = 0

        for line in lines:
            try:
                # Parse line data
                parsed = json.loads(line.parsed_data or '{}')
                ext_no = parsed.get('external_invoice_no', '')
                ext_ver = parsed.get('invoice_version', '')
                ext_doc_ref = parsed.get('external_document_ref', '')
                ext_line_key = parsed.get('external_line_key', '')

                # Technical duplicate detection
                idem_hash = Validator.compute_idempotency_hash(
                    batch.carrier_partner_id.id, ext_no, ext_ver, '')

                # Write document (creates or supersedes)
                doc = Writer.write_document(
                    batch.carrier_partner_id.id,
                    ext_no, ext_ver, ext_doc_ref,
                    template_id=template.id,
                    idempotency_hash=idem_hash,
                    import_batch_id=batch.id,
                )

                # Write billing line
                billing_line = Writer.write_line(
                    doc.id, parsed,
                    external_line_key=ext_line_key,
                    import_line_id=line.id,
                )

                # Update import line status
                line.write({
                    'import_status': 'imported',
                    'billing_line_id': billing_line.id,
                })
                success += 1

            except Exception as e:
                line.write({
                    'import_status': 'failed',
                    'validation_error_message': str(e),
                })
                errors += 1

        batch.write({
            'success_lines': success,
            'error_lines': errors,
            'state': 'completed' if errors == 0 else 'partial_failed',
        })

        return {'status': 'ok', 'success': success, 'errors': errors}

    @api.model
    def validate_import_lines(self, import_batch):
        """Validate all import lines — check field constraints."""
        batch = import_batch
        template = batch.template_id
        Validator = self.env['tlmp.invoice.validator']
        lines = batch.line_ids.filtered(lambda l: l.import_status == 'parsed')
        for line in lines:
            try:
                parsed = json.loads(line.parsed_data or '{}')
                errors = Validator.validate_row(parsed, template)
                if errors:
                    line.write({
                        'import_status': 'failed',
                        'validation_error_code': errors[0][0],
                        'validation_error_message': '; '.join('%s: %s' % e for e in errors),
                    })
                else:
                    line.write({'import_status': 'validated'})
            except Exception as e:
                line.write({
                    'import_status': 'failed',
                    'validation_error_message': str(e),
                })
        batch.write({'state': 'waiting_confirm'})
        return {'status': 'ok'}
