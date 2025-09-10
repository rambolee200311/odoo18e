from odoo import models, fields

class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'
    # 添加允许托盘扫描的功能
    enable_pallet_scanning = fields.Boolean(
        string="Enable Pallet Barcode Scanning",
        help="Allow scanning pallet barcodes during put in pack operation"
    )

    strict_quantity_control = fields.Boolean(
        string='Strict Quantity Control',default=True,
        help='When enabled, requires actual quantity to exactly match demand quantity during validation'
    )

