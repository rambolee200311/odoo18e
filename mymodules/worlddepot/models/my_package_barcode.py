from odoo import api, models, fields
from odoo import http
from odoo.http import request
from odoo.addons.stock_barcode.controllers import stock_barcode


class StockBarcodePackage(models.TransientModel):
    _inherit = "stock.package.destination"

    pallet_name = fields.Char(string="Pallet Barcode", tracking=True)

    @api.model
    def process(self):
        res = super(StockBarcodePackage, self).process()

        # 添加托盘条码扫描处理
        if self.env.context.get('enable_pallet_scanning'):
            if self.pallet_name:
                package = self.move_line_ids.mapped('result_package_id')[:1]
                if package:
                    # 更新包裹的名称
                    package.name = self.pallet_name
                    package.display_name = self.pallet_name
        return res


class PalletAwareStockBarcode(stock_barcode.StockBarcodeController):

    @http.route('/stock_barcode/get_barcode_data', type='json', auth='user')
    def get_barcode_data(self, model, res_id):
        """扩展返回数据，包含托盘扫描功能标记"""
        result = super().get_barcode_data(model, res_id)

        # 如果是包装目标模型，添加托盘扫描标记
        if model == 'stock.package.destination' and res_id:
            package_dest = request.env[model].browse(res_id)
            picking = package_dest.picking_id
            if picking:
                result['data']['enable_pallet_scanning'] = picking.picking_type_id.enable_pallet_scanning

        return result

    @http.route('/stock_barcode/update_pallet', type='json', auth='user')
    def update_pallet(self, pallet_barcode, res_id):
        """
        更新托盘条码
        :param pallet_barcode: 扫描的托盘条码
        :param res_id: stock.package.destination记录ID
        """
        package_dest = request.env['stock.package.destination'].browse(res_id)

        if not package_dest.exists():
            return {'status': 'error', 'message': '记录不存在或已过期'}

        try:
            # 更新pallet_name字段
            package_dest.write({'pallet_name': pallet_barcode})

            # 处理包裹关联逻辑
            move_lines = package_dest.move_line_ids
            package = request.env['stock.quant.package'].search([
                ('name', '=', pallet_barcode)
            ], limit=1)

            if not package:
                package = request.env['stock.quant.package'].create({
                    'name': pallet_barcode
                })

            # 更新所有移动行
            move_lines.write({'result_package_id': package.id})

            return {
                'status': 'success',
                'message': f'托盘 {pallet_barcode} 更新成功',
                'package_id': package.id,
                'package_name': package.name
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
