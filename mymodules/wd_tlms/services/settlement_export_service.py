from odoo import api, fields, models, _


class SettlementExportWizard(models.TransientModel):
    """结算导出向导 — TransientModel"""
    _name = 'tlmp.settlement.export.wizard'
    _description = 'Settlement Export Wizard'

    carrier_partner_id = fields.Many2one(
        'res.partner', string='Carrier',
        domain="[('is_company', '=', True)]")
    period_start = fields.Date(string='Period From', required=True)
    period_end = fields.Date(string='Period To', required=True)
    batch_state = fields.Selection([
        ('', 'All'),
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('processing', 'Processing'),
        ('approved', 'Approved'),
        ('closed', 'Closed'),
    ], string='Batch State')

    def action_export_csv(self):
        """Export settlement data as CSV."""
        domain = [('period_start', '>=', self.period_start),
                  ('period_end', '<=', self.period_end)]
        if self.carrier_partner_id:
            domain.append(('carrier_partner_id', '=', self.carrier_partner_id.id))
        if self.batch_state:
            domain.append(('state', '=', self.batch_state))

        batches = self.env['tlmp.carrier.settlement.batch'].search(domain)

        import csv, io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Batch No.', 'Carrier', 'Period Start', 'Period End',
            'State', 'Document No.', 'Line Total', 'Allocated Amount',
            'Adjustment Amount', 'Final Amount', 'Variance',
        ])
        for batch in batches:
            for line in batch.line_ids:
                doc = line.billing_document_id
                writer.writerow([
                    batch.name, batch.carrier_partner_id.name,
                    batch.period_start, batch.period_end, batch.state,
                    doc.name if doc else '',
                    line.snapshot_amount or 0.0,
                    sum(line.allocation_ids.mapped('allocated_amount')) if line.allocation_ids else 0.0,
                    0.0,  # adjustment amount (future)
                    line.snapshot_amount or 0.0,
                    0.0,  # variance
                ])

        # Create attachment
        filename = 'settlement_export_%s.csv' % fields.Date.today()
        self.env['ir.attachment'].create({
            'name': filename,
            'raw': output.getvalue().encode('utf-8'),
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % filename,
            'target': 'self',
        }


class SettlementExportService(models.AbstractModel):
    """结算导出服务 — 不与 AP 会计接口耦合"""
    _name = 'tlmp.settlement.export.service'
    _description = 'Settlement Export Service'

    @api.model
    def get_export_data(self, carrier_id=False, period_start=False, period_end=False):
        domain = []
        if carrier_id:
            domain.append(('carrier_partner_id', '=', carrier_id))
        if period_start:
            domain.append(('period_start', '>=', period_start))
        if period_end:
            domain.append(('period_end', '<=', period_end))
        return self.env['tlmp.carrier.settlement.batch'].search(domain)
