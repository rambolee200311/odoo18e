# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# ===== Stock Picking 扩展 + F-05状态联动锁 =====
class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound',
                                        readonly=True, copy=False)
    bonded_outbound_id = fields.Many2one('bonded.outbound', string='Bonded Outbound',
                                         readonly=True, copy=False)

    def button_validate(self):
        """V3修正(F-05): 前置校验 + 后置钩子"""
        for picking in self:
            # ---- 入库: bonded.inbound必须是done ----
            if picking.picking_type_code == 'incoming' and picking.bonded_inbound_id:
                if picking.bonded_inbound_id.state != 'done':
                    raise UserError(_(
                        'Cannot validate stock picking: bonded inbound instruction (%s) '
                        'is in state "%s". Inbound instruction must be in "done" state first.'
                        % (picking.bonded_inbound_id.name, picking.bonded_inbound_id.state)
                    ))
            # ---- 出库: bonded.outbound必须是done ----
            if picking.picking_type_code == 'outgoing' and picking.bonded_outbound_id:
                if picking.bonded_outbound_id.state != 'done':
                    raise UserError(_(
                        'Cannot validate stock picking: bonded outbound instruction (%s) '
                        'is in state "%s". Outbound instruction must be in "done" state first.'
                        % (picking.bonded_outbound_id.name, picking.bonded_outbound_id.state)
                    ))
        result = super(StockPicking, self).button_validate()
        # 后处理: 触发指令完成
        for picking in self:
            try:
                if picking.picking_type_code == 'incoming' and picking.bonded_inbound_id:
                    picking.bonded_inbound_id._action_done()
                if picking.picking_type_code == 'outgoing' and picking.bonded_outbound_id:
                    picking.bonded_outbound_id._action_done()
            except Exception as e:
                _logger.error("Error in bonded post-validation for picking %s: %s", picking.name, str(e))
        return result


# ===== Stock Move 扩展 =====
class StockMove(models.Model):
    _inherit = 'stock.move'

    bonded_stock_id = fields.Many2one('bonded.stock', string='Bonded Stock', readonly=True, copy=False)


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


# ===== Inbound Order Charge 扩展 =====
class InboundOrderCharge(models.Model):
    _inherit = 'world.depot.inbound.order.charge'

    gate_arrival_id = fields.Many2one(
        'gate.arrival',
        string='Gate Arrival',
        help='Reference to the gate arrival record for cost splitting',
    )


# ===== Res Users 扩展 =====
class ResUsers(models.Model):
    _inherit = 'res.users'

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Default Warehouse',
        help='Default warehouse for warehouse operations and record rules',
    )
