# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import UserError


def build_pallet_groups(picking, package_field):
    pallet_map = {}
    for move_line in picking.move_line_ids:
        package = move_line[package_field]
        key = package.id or 'no_pallet'
        pallet_group = pallet_map.setdefault(key, {'name': package.name or 'No Pallet', 'move_lines': picking.env['stock.move.line']})
        pallet_group['move_lines'] |= move_line
    return list(pallet_map.values())


class BondedInboundPickingReport(models.AbstractModel):
    _name = 'report.wd_bonded_wms.report_bonded_inbound_picking'
    _description = 'Bonded Inbound Picking Report'

    def _get_report_values(self, docids, data=None):
        docs = self.env['bonded.inbound'].sudo().browse(docids).exists()
        return {'doc_ids': docs.ids, 'doc_model': 'bonded.inbound', 'docs': docs, 'pallet_groups_by_order': {rec.id: build_pallet_groups(rec.picking_id, 'result_package_id') if rec.picking_id else [] for rec in docs}}


class BondedInboundPalletReport(models.AbstractModel):
    _name = 'report.wd_bonded_wms.report_bonded_inbound_pallet'
    _description = 'Bonded Inbound Pallet Report'

    def _get_report_values(self, docids, data=None):
        docs = self.env['bonded.inbound'].sudo().browse(docids).exists()
        pallet_groups_by_order = {}
        for rec in docs:
            if not rec.line_ids or rec.line_ids.filtered(lambda line: not line.package_id):
                raise UserError('Generate packages for every inbound product line before printing the Inbound Pallet Report.')
            pallet_map = {}
            for line in rec.line_ids.filtered('package_id'):
                pallet_group = pallet_map.setdefault(line.package_id.id, {'package': line.package_id, 'lines': rec.env['bonded.inbound.line']})
                pallet_group['lines'] |= line
            pallet_groups_by_order[rec.id] = list(pallet_map.values())
        return {'doc_ids': docs.ids, 'doc_model': 'bonded.inbound', 'docs': docs, 'pallet_groups_by_order': pallet_groups_by_order}


class BondedOutboundPickingReport(models.AbstractModel):
    _name = 'report.wd_bonded_wms.report_bonded_outbound_picking'
    _description = 'Bonded Outbound Picking Report'

    def _get_report_values(self, docids, data=None):
        docs = self.env['bonded.outbound'].sudo().browse(docids).exists()
        return {'doc_ids': docs.ids, 'doc_model': 'bonded.outbound', 'docs': docs, 'pallet_groups_by_order': {rec.id: build_pallet_groups(rec.picking_id, 'package_id') if rec.picking_id else [] for rec in docs}}
