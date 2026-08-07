from odoo import api, fields, models, _


class CarrierInvoiceImport(models.Model):
    """承运商账单导入批次 — 外部账单进入 Settlement Domain 的标准入口"""
    _name = 'tlmp.carrier.invoice.import'
    _description = 'Carrier Invoice Import Batch'
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(string='Import Batch', required=True, copy=False,
                       default=lambda self: _('New'))
    carrier_partner_id = fields.Many2one(
        'res.partner', string='Carrier',
        domain="[('is_company', '=', True)]", required=True)
    template_id = fields.Many2one(
        'tlmp.carrier.invoice.template', string='Template')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('uploaded', 'Uploaded'),
        ('preview', 'Preview'),
        ('validating', 'Validating'),
        ('validated', 'Validated'),
        ('waiting_confirm', 'Waiting Confirmation'),
        ('importing', 'Importing'),
        ('completed', 'Completed'),
        ('partial_failed', 'Partially Failed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True)
    file_name = fields.Char(string='File Name')
    file_data = fields.Binary(string='File', attachment=True)
    total_lines = fields.Integer(string='Total Lines', default=0)
    success_lines = fields.Integer(string='Success Lines', default=0)
    error_lines = fields.Integer(string='Error Lines', default=0)
    line_ids = fields.One2many(
        'tlmp.carrier.invoice.import.line', 'import_id',
        string='Import Lines')
    billing_document_id = fields.Many2one(
        'tlmp.carrier.billing.document', string='Created Document',
        readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tlmp.invoice.import.seq') or _('New')
        return super().create(vals_list)

    def action_preview(self):
        self.write({'state': 'preview'})

    def action_validate(self):
        self.write({'state': 'validating'})

    def action_confirm_import(self):
        self.write({'state': 'importing'})

    def action_import(self):
        self.write({'state': 'importing'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})


class CarrierInvoiceImportLine(models.Model):
    """导入行明细 — 临时导入层，非业务事实
    确认后业务数据进入 billing.line，本行仅保留原始数据和错误记录。
    """
    _name = 'tlmp.carrier.invoice.import.line'
    _description = 'Invoice Import Line'
    _order = 'import_id, line_no'

    import_id = fields.Many2one(
        'tlmp.carrier.invoice.import', string='Import Batch',
        required=True, ondelete='cascade')
    line_no = fields.Integer(string='Line No.', required=True)
    raw_data = fields.Text(
        string='Raw Data (JSON)',
        help='原始数据 JSON 格式（CSV 行为数组）')
    parsed_data = fields.Text(
        string='Parsed Data (JSON)',
        help='解析后结构化数据')
    billing_line_id = fields.Many2one(
        'tlmp.carrier.billing.line', string='Created Billing Line',
        readonly=True)
    import_status = fields.Selection([
        ('pending', 'Pending'),
        ('parsed', 'Parsed'),
        ('validated', 'Validated'),
        ('waiting_confirm', 'Waiting Confirmation'),
        ('imported', 'Imported'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ], string='Import Status', default='pending')
    validation_error_code = fields.Char(string='Error Code')
    validation_error_message = fields.Text(string='Error Message')
