# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BondedValueLimit(models.Model):
    _name = 'bonded.value.limit'
    _description = 'Bonded Value Limit - 货值上限管理'
    _rec_name = 'bonded_book_id'
    _order = 'bonded_book_id, effective_date desc'

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True,
                                     ondelete='cascade', index=True)
    project_id = fields.Many2one('project.project', string='Project', ondelete='restrict', index=True)
    total_value = fields.Monetary(string='Total Value Limit', required=True)
    used_value = fields.Monetary(string='Used Value', compute='_compute_usage', store=True)
    available_value = fields.Monetary(string='Available Value', compute='_compute_usage', store=True)
    currency_id = fields.Many2one('res.currency', related='bonded_book_id.currency_id', string='Currency', readonly=True)
    effective_date = fields.Date(string='Effective Date', required=True)
    expiry_date = fields.Date(string='Expiry Date')
    state = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
    ], string='Status', default='active', required=True)

    @api.depends('bonded_book_id.value_ledger_ids.project_id', 'bonded_book_id.value_ledger_ids.reserved_change', 'bonded_book_id.value_ledger_ids.deducted_change', 'project_id', 'total_value')
    def _compute_usage(self):
        env_value_ledger = self.env['bonded.value.ledger'].sudo()
        for rec in self:
            ledger_records = env_value_ledger.search([('bonded_book_id', '=', rec.bonded_book_id.id), ('project_id', '=', rec.project_id.id)])
            rec.used_value = sum(ledger_records.mapped('reserved_change')) + sum(ledger_records.mapped('deducted_change'))
            rec.available_value = rec.total_value - rec.used_value

    @api.constrains('bonded_book_id', 'project_id', 'total_value')
    def check_project_total_value_limit(self):
        for rec in self:
            if rec.project_id and rec.total_value > rec.bonded_book_id.company_total_value_limit:
                raise ValidationError(_('Project value limit cannot exceed the company total value limit.'))

    def _release_value(self, stock_ids):
        """释放额度 - 由出库指令完成时调用"""
        # 额度释放逻辑: used_value 由 compute 自动计算
        pass
