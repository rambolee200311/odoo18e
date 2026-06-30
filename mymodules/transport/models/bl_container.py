from odoo import models, fields, api
from odoo.exceptions import UserError


class BLContainer(models.Model):
    _name = 'bl.container'
    _description = '提单柜号关联'
    _rec_name = 'container_no'

    bl_no = fields.Char('提单号', required=True)
    container_no = fields.Char('柜号', required=True)
    container_type = fields.Char('箱型')
    supplier = fields.Char('发货方')
    destination_warehouse = fields.Many2one('stock.warehouse', string='目的仓库',
                                             ondelete='set null')
    state = fields.Selection([
        ('draft', '待安排'),
        ('planned', '已排期'),
        ('done', '运输完成')
    ], default='draft', string='状态')

    _sql_constraints = [
        ('container_no_unique', 'UNIQUE(container_no)', '柜号不能重复！')
    ]

    @api.constrains('destination_warehouse')
    def _check_destination_warehouse(self):
        """检查目的仓库是否有效"""
        for record in self:
            if record.destination_warehouse:
                # 验证仓库是否存在
                warehouse = self.env['stock.warehouse'].browse(record.destination_warehouse.id)
                if not warehouse.exists():
                    record.destination_warehouse = False

    @api.model
    def get_unplanned_containers(self):
        """
        自定义ORM方法：查询所有待安排的集装箱
        """
        containers = self.search([('state', '=', 'draft')])
        result = []
        for container in containers:
            vals = {
                'id': container.id,
                'container_no': container.container_no,
                'bl_no': container.bl_no,
                'container_type': container.container_type,
                'state': container.state,
            }
            # 安全处理 Many2one 字段
            if container.destination_warehouse:
                wh = container.destination_warehouse
                if wh.exists():
                    # vals['destination_warehouse'] = (wh.id, wh.display_name)
                    vals['destination_warehouse'] = wh.id
                else:
                    vals['destination_warehouse'] = False
            else:
                vals['destination_warehouse'] = False
            result.append(vals)
        return result
