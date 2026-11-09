# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


# ===== Stock Picking 扩展 + F-05状态联动锁 =====
class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound',
                                        readonly=True, copy=False)
    bonded_outbound_id = fields.Many2one('bonded.outbound', string='Bonded Outbound',
                                         readonly=True, copy=False)
    unique_identifier_no = fields.Char(string='Unique Identifier No.', readonly=True, copy=False, index=True)
    bonded_customs_file_id = fields.Many2one('bonded.customs.file', string='Customs / Clearance File', readonly=True, copy=False, ondelete='restrict', index=True)
    customs_file_status = fields.Selection(related='bonded_customs_file_id.state', string='Customs File Status', store=True, readonly=True, index=True)
    bonded_flag = fields.Selection([('bonded', 'Bonded'), ('non_bonded', 'Non-bonded')], string='Bonded Flag', compute='_compute_bonded_flag', store=True, readonly=True, index=True)
    t1_is_closed = fields.Boolean(string='T1 Closed', compute='_compute_t1_is_closed', store=True, readonly=True, index=True)
    t1_closed_date = fields.Datetime(related='bonded_customs_file_id.t1_closed_date', string='T1 Closed Date', store=True, readonly=True, index=True)
    mrn = fields.Char(related='bonded_customs_file_id.mrn', string='MRN', store=True, readonly=True, index=True)
    mrn_status = fields.Selection(related='bonded_customs_file_id.mrn_id.state', string='MRN Status', store=True, readonly=True, index=True)

    @api.depends('bonded_customs_file_id.declaration_type', 'bonded_customs_file_id.state')
    def _compute_t1_is_closed(self):
        for rec in self:
            rec.t1_is_closed = rec.bonded_customs_file_id.declaration_type in ('t1_in', 't1_out') and rec.bonded_customs_file_id.state == 'done'

    @api.depends('bonded_customs_file_id.declaration_type')
    def _compute_bonded_flag(self):
        for rec in self:
            rec.bonded_flag = 'non_bonded' if rec.bonded_customs_file_id.declaration_type == 'clearance_out' else 'bonded' if rec.bonded_customs_file_id else False

    def unlink(self):
        for rec in self:
            inbound = rec.bonded_inbound_id
            if inbound and rec.state != 'done' and inbound.picking_id == rec:
                vals = {'picking_id': False}
                if inbound.state == 'in_progress':
                    vals['state'] = 'released'
                inbound.write(vals)
        return super().unlink()
    @api.model
    def action_create_bonded_pda_internal_transfer(self):
        warehouse = self.env.user.warehouse_id
        if not warehouse:
            raise UserError(_('Set a default warehouse on your user before starting an internal transfer.'))
        return self.action_create_pda_internal_transfer(warehouse.id)

    def button_validate(self):
        """V3修正(F-05): 前置校验 + 后置钩子"""
        for picking in self:
            if picking.state not in ('done', 'cancel'):
                if picking.picking_type_code == 'incoming' and picking.bonded_inbound_id and picking.bonded_inbound_id.project_id.barcode_scan_mode == 'custom':
                    package_lines = picking.move_line_ids.filtered(lambda line: line.result_package_id and line.quantity > 0)
                    if picking.bonded_inbound_id.package_generation_mode != 'none' and not package_lines:
                        raise UserError(_('Bonded inbound picking has no pallet lines to scan.'))
                    missing = package_lines.filtered(lambda line: not line.is_location_updated or not line.location_dest_id)
                    if missing:
                        raise UserError(_('Please scan locations for all bonded inbound pallets: %s') % ', '.join(sorted(set(missing.mapped('result_package_id.name')))))
                if picking.picking_type_code == 'outgoing' and picking.bonded_outbound_id and picking.bonded_outbound_id.project_id.barcode_scan_mode == 'custom':
                    lines = picking.move_line_ids.filtered(lambda line: line.quantity > 0 and line.state != 'cancel')
                    if not lines or lines.filtered(lambda line: not line.package_id or not line.is_outbound_scanned or float_compare(line.outbound_scanned_quantity, line.quantity, precision_rounding=line.product_uom_id.rounding) != 0):
                        raise UserError(_('Please complete bonded outbound pallet and product scanning before validating.'))
            # ---- 入库: bonded.inbound必须是done ----
            if picking.picking_type_code == 'incoming' and picking.bonded_inbound_id:
                if picking.bonded_inbound_id.state != 'in_progress':
                    raise UserError(_(
                        'Cannot validate stock picking: bonded inbound instruction (%s) '
                        'is in state "%s". Inbound instruction must be in "in progress" state first.'
                        % (picking.bonded_inbound_id.name, picking.bonded_inbound_id.state)
                    ))
            # ---- 出库: bonded.outbound必须是done ----
            if picking.picking_type_code == 'outgoing' and picking.bonded_outbound_id:
                if picking.bonded_outbound_id.state != 'in_progress':
                    raise UserError(_(
                        'Cannot validate stock picking: bonded outbound instruction (%s) '
                        'is in state "%s". Outbound instruction must be in "in progress" state first.'
                        % (picking.bonded_outbound_id.name, picking.bonded_outbound_id.state)
                    ))
        result = super(StockPicking, self).button_validate()
        # 后处理: 触发指令完成
        for picking in self:
            if picking.picking_type_code == 'incoming' and picking.bonded_inbound_id and picking.state == 'done' and picking.bonded_inbound_id.state == 'in_progress':
                picking.bonded_inbound_id.action_done()
            if picking.picking_type_code == 'outgoing' and picking.bonded_outbound_id:
                try:
                    picking.bonded_outbound_id.action_done()
                except Exception as e:
                    _logger.error("Error in bonded post-validation for picking %s: %s", picking.name, str(e))
        return result


# ===== Stock Move 扩展 =====
class StockMove(models.Model):
    _inherit = 'stock.move'

    bonded_stock_id = fields.Many2one('bonded.stock', string='Bonded Stock', readonly=True, copy=False)
    bonded_inbound_line_id = fields.Many2one('bonded.inbound.line', string='Bonded Inbound Line', readonly=True, copy=False)
    bonded_outbound_line_id = fields.Many2one('bonded.outbound.line', string='Bonded Outbound Line', readonly=True, copy=False)


# ===== Stock Location 扩展 =====
class StockLocation(models.Model):
    _inherit = 'stock.location'

    is_bonded = fields.Boolean(string='Bonded Warehouse', default=False, tracking=True)
    bonded_location_type = fields.Selection([
        ('bonded_storage', 'Bonded Storage Area'),
        ('bonded_quarantine', 'Bonded Quarantine Area'),
        ('non_bonded', 'Non-bonded Area'),
    ], string='Bonded Location Type', default='non_bonded')


# ===== Stock Lot 扩展 =====
class StockLot(models.Model):
    _inherit = 'stock.lot'

    bonded_book_id = fields.Many2one('bonded.book', string='Bonded Book', readonly=True)
    current_customs_status = fields.Selection([
        ('entrepot', 'Entrepot'),
        ('vrij', 'Vrij'),
        ('in_t1_transit', 'In T1 Transit'),
    ], string='Customs Status', readonly=True)


# ===== Product Product 扩展 =====
class ProductProduct(models.Model):
    _inherit = 'product.product'

    bonded_product_filing_ids = fields.One2many('bonded.product', 'product_id',
                                                string='Bonded Product Filings')


# ===== Res Users 扩展 =====
class ResUsers(models.Model):
    _inherit = 'res.users'

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Default Warehouse',
        help='Default warehouse for warehouse operations and record rules',
    )


class ResPartner(models.Model):
    _inherit = 'res.partner'

    eori_number = fields.Char(string='Default EORI Number', index=True)
    eori_valid_until = fields.Date(string='EORI Valid Until')
    vat_number = fields.Char(string='VAT Number', index=True)
    eori_entity_lines = fields.One2many('bonded.eori.entity', 'partner_id', string='EORI Entities')
    customs_authorization_lines = fields.One2many('bonded.customs.authorization', 'partner_id', string='Customs Authorizations')


class ResCompany(models.Model):
    _inherit = 'res.company'

    eori_number = fields.Char(string='EORI Number', index=True)
    warehouse_license_no = fields.Char(string='Bonded Warehouse License No.', index=True)
    warehouse_license_expiry = fields.Date(string='Bonded Warehouse License Expiry')
