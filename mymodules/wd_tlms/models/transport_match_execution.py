from odoo import api, fields, models, _


class CarrierMatchExecution(models.Model):
    """自动匹配执行批次 — 审计边界"""
    _name = 'tlmp.carrier.match.execution'
    _description = 'Match Execution Batch'
    _rec_name = 'name'
    _order = 'start_time desc'

    name = fields.Char(string='Execution Batch', required=True, copy=False,
                       default=lambda self: _('New'))
    state = fields.Selection([
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], string='Status', default='running', required=True)
    operator = fields.Many2one('res.users', string='Operator',
                               default=lambda self: self.env.uid)
    start_time = fields.Datetime(
        string='Start Time', default=fields.Datetime.now)
    end_time = fields.Datetime(string='End Time')
    matched_count = fields.Integer(string='Matched', default=0)
    failed_count = fields.Integer(string='Failed', default=0)
    suggestion_ids = fields.One2many(
        'tlmp.carrier.match.suggestion', 'execution_id',
        string='Suggestions')
    history_ids = fields.One2many(
        'tlmp.carrier.matching.history', 'execution_id',
        string='History')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tlmp.match.execution.seq') or _('New')
        return super().create(vals_list)

    def _done(self, matched=0, failed=0, state='completed'):
        self.write({
            'state': state,
            'end_time': fields.Datetime.now(),
            'matched_count': matched,
            'failed_count': failed,
        })
