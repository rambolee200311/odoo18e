from odoo import models, api, fields, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    allow_duplicate_serial = fields.Boolean(
        string='Allow Duplicate Serial Numbers',
        help='Allow multiple serial numbers with the same value for products in this category'
    )

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """在验证前处理序列号冲突"""
        try:
            # 处理扫描条码导致的序列号重用问题
            self._fix_scanned_serial_reuse()
        except Exception as e:
            _logger.error("Failed to fix serial reuse: %s", str(e))
            # 如果修复失败，尝试强制验证
            return self._force_validate_with_error_handling(e)
        
        return super().button_validate()

    def _fix_scanned_serial_reuse(self):
        """修复扫描条码导致的序列号重用问题"""
        for move_line in self.move_line_ids:
            if self._should_fix_serial_reuse(move_line):
                self._rename_and_recreate_serial(move_line)

    def _should_fix_serial_reuse(self, move_line):
        """检查是否需要修复序列号重用"""
        if not move_line.product_id or move_line.product_id.tracking != 'serial':
            return False
            
        if not move_line.lot_id:
            return False
            
        # 检查是否允许重复序列号
        if not self._allow_duplicate_serial(move_line.product_id):
            return False
            
        # 检查是否是从其他调拨单复用的序列号（lot_name为空）
        return not move_line.lot_name

    def _allow_duplicate_serial(self, product):
        """检查产品类别是否允许重复序列号"""
        category = product.categ_id
        while category:
            if category.allow_duplicate_serial:
                return True
            category = category.parent_id
        return False

    def _rename_and_recreate_serial(self, move_line):
        """重命名现有序列号并创建新序列号"""
        try:
            existing_serial = move_line.lot_id
            product = move_line.product_id
            original_name = existing_serial.name
            
            _logger.info("Fixing serial reuse: %s for product %s", original_name, product.display_name)
            
            # 1. 重命名现有序列号
            new_name = self._generate_unique_name(original_name, product)
            existing_serial.name = new_name
            _logger.info("Renamed existing serial from %s to %s", original_name, new_name)
            
            # 2. 用原始名称创建新序列号
            new_serial = self.env['stock.lot'].create({
                'name': original_name,
                'product_id': product.id,
                'company_id': self.company_id.id,
            })
            
            # 3. 更新移动行指向新序列号
            move_line.lot_id = new_serial.id
            move_line.lot_name = original_name  # 设置序列号名称
            
            _logger.info("Created new serial %s and updated move line", original_name)
            
        except UserError as e:
            # 如果是唯一性约束错误，尝试其他方法
            if "already been assigned" in str(e):
                _logger.warning("Serial creation failed due to constraint, trying alternative approach")
                self._handle_serial_creation_failure(move_line, original_name, str(e))
            else:
                raise
        except Exception as e:
            _logger.error("Unexpected error in _rename_and_recreate_serial: %s", str(e))
            raise

    def _handle_serial_creation_failure(self, move_line, original_name, error_msg):
        """处理序列号创建失败的情况"""
        _logger.warning("Handling serial creation failure for %s: %s", original_name, error_msg)
        
        # 方法1: 尝试查找现有的序列号
        existing_serial = self.env['stock.lot'].search([
            ('name', '=', original_name),
            ('product_id', '=', move_line.product_id.id),
            ('company_id', 'in', [False, self.company_id.id])
        ], limit=1)
        
        if existing_serial:
            move_line.lot_id = existing_serial.id
            move_line.lot_name = original_name
            _logger.info("Used existing serial %s after creation failed", original_name)
            return
        
        # 方法2: 生成新的唯一名称
        new_name = self._generate_unique_name(original_name, move_line.product_id)
        new_serial = self.env['stock.lot'].create({
            'name': new_name,
            'product_id': move_line.product_id.id,
            'company_id': self.company_id.id,
        })
        move_line.lot_id = new_serial.id
        move_line.lot_name = new_name
        _logger.info("Created serial with alternative name %s", new_name)

    def _generate_unique_name(self, base_name, product):
        """生成唯一的序列号名称"""
        counter = 1
        max_attempts = 100
        
        while counter <= max_attempts:
            new_name = f"{base_name}_RENAMED_{counter}"
            if not self.env['stock.lot'].search([
                ('name', '=', new_name), 
                ('product_id', '=', product.id)
            ]):
                return new_name
            counter += 1
        
        # 如果尝试多次都失败，抛出异常
        raise UserError(_("Cannot generate unique serial name for %s after %d attempts") % (base_name, max_attempts))

    def _force_validate_with_error_handling(self, original_error):
        """处理修复失败时的强制验证"""
        _logger.warning("Serial fix failed, attempting force validation: %s", str(original_error))
        
        try:
            # 尝试基本修复
            for move_line in self.move_line_ids:
                if move_line.lot_id and not move_line.lot_name:
                    move_line.lot_name = move_line.lot_id.name
                elif move_line.lot_name and not move_line.lot_id:
                    # 尝试创建序列号，忽略错误
                    try:
                        new_serial = self.env['stock.lot'].create({
                            'name': move_line.lot_name,
                            'product_id': move_line.product_id.id,
                            'company_id': self.company_id.id,
                        })
                        move_line.lot_id = new_serial.id
                    except:
                        # 如果创建失败，跳过此移动行
                        continue
            
            # 强制验证，跳过所有检查
            return super(StockPicking, self.with_context(
                skip_sanity_check=True,
                skip_serial_check=True
            )).button_validate()
            
        except Exception as e:
            _logger.error("Force validation also failed: %s", str(e))
            # 返回原始错误
            raise original_error

    def _rename_and_recreate_serial_with_fallback(self, move_line):
        """带降级处理的序列号重命名和重建"""
        try:
            self._rename_and_recreate_serial(move_line)
        except Exception as e:
            _logger.error("Primary serial fix failed, using fallback: %s", str(e))
            self._fallback_serial_fix(move_line)

    def _fallback_serial_fix(self, move_line):
        """降级处理：简单的序列号修复"""
        try:
            if move_line.lot_id and not move_line.lot_name:
                # 简单设置序列号名称
                move_line.lot_name = move_line.lot_id.name
                _logger.info("Fallback: Set lot_name to %s", move_line.lot_id.name)
            elif not move_line.lot_id and move_line.lot_name:
                # 尝试创建序列号，如果失败则清除序列号名称
                try:
                    new_serial = self.env['stock.lot'].create({
                        'name': move_line.lot_name,
                        'product_id': move_line.product_id.id,
                        'company_id': self.company_id.id,
                    })
                    move_line.lot_id = new_serial.id
                    _logger.info("Fallback: Created new serial %s", move_line.lot_name)
                except:
                    move_line.lot_name = False
                    _logger.warning("Fallback: Cleared lot_name due to creation failure")
        except Exception as e:
            _logger.error("Fallback serial fix also failed: %s", str(e))
            # 最后手段：跳过此移动行
            move_line.lot_name = False
            move_line.lot_id = False