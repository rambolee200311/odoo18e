import json
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InvoiceWriter(models.AbstractModel):
    _name = 'tlmp.invoice.writer'
    _description = 'Invoice Writer — Line-isolated billing creation with version supersede'

    @api.model
    def write_document(self, carrier_id, external_invoice_no, invoice_version,
                       external_document_ref, template_id=False,
                       idempotency_hash='', file_checksum='',
                       import_batch_id=False):
        """Create billing.document from import data. If a previous version exists,
        mark it as superseded (immutable)."""
        # Check if previous version exists for supersede
        if external_invoice_no and invoice_version:
            old_docs = self.env['tlmp.carrier.billing.document'].search([
                ('carrier_id', '=', carrier_id),
                ('external_invoice_no', '=', external_invoice_no),
                ('state', '=', 'active'),
            ])
            for old in old_docs:
                old.write({'state': 'superseded'})

        doc = self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': carrier_id,
            'external_invoice_no': external_invoice_no,
            'invoice_version': invoice_version,
            'external_document_ref': external_document_ref,
            'idempotency_hash': idempotency_hash,
            'file_checksum': file_checksum,
            'import_batch_id': import_batch_id,
            'state': 'active',
        })
        return doc

    @api.model
    def write_line(self, document_id, parsed, external_line_key, import_line_id=False):
        """Create a single billing.line. line-isolated — caller manages transaction."""
        vals = {
            'document_id': document_id,
            'external_line_key': external_line_key,
            'raw_description': parsed.get('raw_description', ''),
            'carrier_reference': parsed.get('carrier_reference', ''),
            'raw_reference': parsed.get('raw_reference', ''),
            'service_date': parsed.get('service_date') or False,
            'net_amount': float(parsed.get('net_amount', 0)),
            'tax': float(parsed.get('tax', 0)),
        }
        if import_line_id:
            vals['import_line_id'] = import_line_id
        charge_code = parsed.get('charge_type_code')
        if charge_code:
            charge = self.env['tlmp.carrier.charge.type'].search(
                [('code', '=', charge_code)], limit=1)
            if charge:
                vals['charge_type_id'] = charge.id

        line = self.env['tlmp.carrier.billing.line'].create(vals)
        return line
