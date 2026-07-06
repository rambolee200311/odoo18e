# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CustomsFileCreateFromHandover(models.TransientModel):
    _name = 'customs.file.create.from.handover'
    _description = 'Wizard: Create Customs Declaration from Handover'

    handover_id = fields.Many2one('operation.order.handover', string='Handover', required=True)
    declaration_type = fields.Selection([
        ('t1_in', 'T1 Transit Inbound'),
        ('b3_in', 'B3 Bonded Inbound'),
        ('b3_out', 'B3 Customs Clearance (L2F)'),
    ], string='Declaration Type', required=True, default='t1_in')
    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', required=True,
                                     domain=[('state', '=', 'active')])

    # R5: 自动填充的pre_mrn_ids
    suggested_pre_mrn_ids = fields.Text(string='Suggested Pre-condition MRNs', readonly=True,
                                        help='Auto-retrieved from completed T1s under this handover')

    @api.onchange('handover_id', 'declaration_type')
    def _onchange_suggest_mrns(self):
        """R5: 自动检索已完成的T1并建议作为pre_mrn"""
        if self.declaration_type == 'b3_in' and self.handover_id:
            # 查找该handover下所有已done的T1 customs.file
            t1_files = self.env['bonded.customs.file'].search([
                ('handover_id', '=', self.handover_id.id),
                ('declaration_type', '=', 't1_in'),
                ('state', '=', 'done'),
            ])
            if t1_files:
                mrns = [f.mrn for f in t1_files if f.mrn]
                self.suggested_pre_mrn_ids = ', '.join(mrns)
            else:
                self.suggested_pre_mrn_ids = _('No completed T1 declarations found for this handover.')

    def action_create(self):
        self.ensure_one()
        # 自动填充handover数据到customs.file
        waybill = self.handover_id.waybill_id
        vals = {
            'bonded_book_id': self.bonded_book_id.id,
            'declaration_type': self.declaration_type,
            'customs_code': waybill.project.customs_office_code or '',
            'consignor_eori': waybill.shipper.eori_no if hasattr(waybill.shipper, 'eori_no') else '',
            'consignee_eori': waybill.consignee.eori_no if hasattr(waybill.consignee, 'eori_no') else '',
            'origin_country_id': waybill.origin_country_id.id if waybill.origin_country_id else False,
            'handover_id': self.handover_id.id,
            'previous_doc_no': self.handover_id.do_no or '',
        }
        # B3 with T1 source: set pre_condition
        if self.declaration_type == 'b3_in':
            t1_done = self.env['bonded.customs.file'].search([
                ('handover_id', '=', self.handover_id.id),
                ('declaration_type', '=', 't1_in'),
                ('state', '=', 'done'),
            ], limit=1)
            if t1_done:
                vals['pre_condition'] = 't1_closed'

        customs_file = self.env['bonded.customs.file'].create(vals)

        # 填充pre_mrn_ids (R5)
        if self.declaration_type == 'b3_in' and self.suggested_pre_mrn_ids and self.suggested_pre_mrn_ids != _('No completed T1 declarations found for this handover.'):
            for mrn in self.suggested_pre_mrn_ids.split(', '):
                mrn = mrn.strip()
                if mrn:
                    self.env['customs.file.pre.mrn'].create({
                        'customs_file_id': customs_file.id,
                        'mrn': mrn,
                    })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'bonded.customs.file',
            'res_id': customs_file.id,
            'view_mode': 'form',
            'target': 'current',
        }