from odoo import models, fields, api
from datetime import datetime

class ContainerTransportPlan(models.Model):
    _name = 'container.transport.plan'
    _description = '集装箱运输计划'

    container_id = fields.Many2one('bl.container', string='集装箱', required=True, ondelete='cascade')
    plan_date = fields.Date('计划运输日期', required=True)
    transport_company = fields.Char('承运商')
    remark = fields.Char('备注')
    state = fields.Selection([
        ('draft', '新增'),
        ('in_progress', '进行中'),
        ('done', '完成'),
        ('cancel', '取消')
    ], default='draft', string='计划状态', required=True)
    
    container_no = fields.Char('柜号', related='container_id.container_no', store=True)
    bl_no = fields.Char('提单号', related='container_id.bl_no', store=True)

    @api.model
    def create_transport_plan(self, container_id, plan_date, transport_company='', remark=''):
        """
        创建运输计划
        """
        plan = self.create({
            'container_id': container_id,
            'plan_date': plan_date,
            'transport_company': transport_company,
            'remark': remark,
            'state': 'draft'
        })
        self.env['bl.container'].browse(container_id).write({'state': 'planned'})
        return plan.id

    @api.model
    def update_transport_plan(self, plan_id, update_data):
        """
        更新运输计划
        """
        plan = self.browse(plan_id)
        if not plan.exists():
            raise ValueError(f"运输计划ID {plan_id} 不存在")
        
        plan.write(update_data)
        
        container = plan.container_id
        if update_data.get('state') == 'cancel':
            container.write({'state': 'draft'})
        elif update_data.get('state') == 'done':
            container.write({'state': 'done'})
        
        return True

    @api.model
    def delete_transport_plan(self, plan_id):
        """
        删除运输计划，恢复集装箱状态为待安排
        """
        plan = self.browse(plan_id)
        if not plan.exists():
            raise ValueError(f"运输计划ID {plan_id} 不存在")
        
        container_id = plan.container_id.id
        plan.unlink()
        
        # 恢复集装箱状态
        self.env['bl.container'].browse(container_id).write({'state': 'draft'})
        return True

    @api.model
    def get_plans_by_date_range(self, start_date, end_date):
        """
        获取指定日期范围内的运输计划
        """
        plans = self.search([
            ('plan_date', '>=', start_date),
            ('plan_date', '<=', end_date)
        ])
        return plans.read(['id', 'container_id', 'plan_date', 'container_no', 'bl_no', 'container_type'])

    @api.model
    def get_daily_plan_summary(self, start_date, end_date):
        """
        获取每日计划汇总（用于日历显示）
        """
        plans = self.search([
            ('plan_date', '>=', start_date),
            ('plan_date', '<=', end_date)
        ])
        
        summary = {}
        for plan in plans:
            date_str = plan.plan_date.strftime('%Y-%m-%d')
            if date_str not in summary:
                summary[date_str] = {
                    'count': 0,
                    'containers': []
                }
            summary[date_str]['count'] += 1
            summary[date_str]['containers'].append({
                'id': plan.id,
                'container_no': plan.container_no,
                'bl_no': plan.bl_no,
                'container_type': plan.container_id.container_type or '',
                'container_id': [plan.container_id.id, plan.container_no]
            })
        
        return summary
