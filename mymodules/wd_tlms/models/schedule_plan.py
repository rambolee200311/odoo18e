# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SchedulePlanSchedule(models.Model):
    """排期计划 - Sprint2 核心模型

    链接 pickup.plan 到具体排期日期，支持集装箱/托件双货型，
    提供状态流转、时间段防重叠、排期/取消排期业务逻辑。
    计划驱动型场景（warehouse/warehouse_transfer）使用该模型。
    """
    _name = 'schedule.plan.schedule'
    _description = 'Schedule Plan'
    _order = 'scheduled_date, plan_id'
    _rec_name = 'display_name'

    # -----------------------------------------------------------
    # 核心关联
    # -----------------------------------------------------------
    plan_id = fields.Many2one(
        'pickup.plan', string='Pickup Plan',
        required=True, ondelete='cascade', index=True)
    pickup_plan_id = fields.Many2one(
        'pickup.plan', string='Pickup Plan',
        ondelete='set null', index=True,
        help='Pickup plan created from this schedule record.')

    container_line_id = fields.Many2one(
        'pickup.plan.container.line', string='Container Line',
        ondelete='set null', index=True,
        help='For container cargo: which specific container line is scheduled')

    # -----------------------------------------------------------
    # 排期字段
    # -----------------------------------------------------------
    scheduled_date = fields.Date(
        string='Scheduled Date', required=True, index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True,
        help='draft → scheduled → completed / cancelled')

    # -----------------------------------------------------------
    # 显示字段（related/计算，用于日历列表展示）
    # -----------------------------------------------------------
    display_name = fields.Char(
        string='Display Name', compute='_compute_display_name', store=True)
    cargo_type = fields.Selection(
        related='plan_id.cargo_type', string='Cargo Type', store=True)
    destination_type = fields.Selection(
        related='plan_id.destination_type', string='Destination', store=True)
    warehouse_id = fields.Many2one(
        related='plan_id.warehouse_id', string='Warehouse', store=True)
    source_warehouse_id = fields.Many2one(
        related='plan_id.source_warehouse_id', string='Source Warehouse', store=True)
    pallet_count = fields.Integer(
        related='plan_id.pallet_count', string='Pallets', readonly=True)
    cargo_weight = fields.Float(
        related='plan_id.cargo_weight', string='Weight (kg)', readonly=True)
    cargo_description = fields.Text(
        related='plan_id.cargo_description', string='Cargo Description', readonly=True)

    # 集装箱维度的显示字段
    container_number = fields.Char(
        related='container_line_id.container_number',
        string='Container No.', store=True, readonly=True)
    container_type = fields.Selection(
        related='container_line_id.container_type',
        string='Container Type', store=True, readonly=True)
    bl_number = fields.Char(
        related='container_line_id.bl_number',
        string='BL No.', readonly=True)

    # -----------------------------------------------------------
    # 元数据
    # -----------------------------------------------------------
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    # -----------------------------------------------------------
    # SQL 约束：同一集装箱不可在同一天被排期两次
    # -----------------------------------------------------------
    _sql_constraints = [
        ('unique_container_date', 'UNIQUE(container_line_id, scheduled_date)',
         _('This container is already scheduled on this date! Please choose another date or check the schedule.')),
    ]

    # -----------------------------------------------------------
    # 计算字段
    # -----------------------------------------------------------
    @api.depends('plan_id.name', 'container_line_id.container_number', 'scheduled_date')
    def _compute_display_name(self):
        for rec in self:
            if rec.container_line_id and rec.container_line_id.container_number:
                rec.display_name = '%s - %s' % (
                    rec.container_line_id.container_number,
                    rec.scheduled_date or '')
            else:
                rec.display_name = '%s - %s' % (
                    rec.plan_id.name,
                    rec.scheduled_date or '')

    # -----------------------------------------------------------
    # 业务方法
    # -----------------------------------------------------------
    def action_schedule(self):
        """将排期记录标记为已排期，同步写入 pickup.plan.scheduled_date"""
        for rec in self:
            rec.state = 'scheduled'
            if rec.plan_id:
                rec.plan_id.scheduled_date = rec.scheduled_date

    def action_complete(self):
        """标记排期完成"""
        self.state = 'completed'

    def action_cancel(self):
        """取消排期，清除计划单的 scheduled_date（如无其他有效排期）"""
        for rec in self:
            rec.state = 'cancelled'
            if rec.plan_id:
                # 检查该计划是否还有其他有效排期
                other = self.search([
                    ('plan_id', '=', rec.plan_id.id),
                    ('state', '=', 'scheduled'),
                    ('id', '!=', rec.id),
                ], limit=1)
                if not other:
                    rec.plan_id.scheduled_date = False

    def action_draft(self):
        """退回草稿"""
        self.state = 'draft'

    # -----------------------------------------------------------
    # Override create: 自动设置 plan scheduled_date
    # -----------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.plan_id and rec.state == 'scheduled':
                rec.plan_id.scheduled_date = rec.scheduled_date
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'scheduled_date' in vals or 'state' in vals:
            for rec in self:
                if rec.state == 'scheduled' and rec.plan_id:
                    rec.plan_id.scheduled_date = rec.scheduled_date
                elif rec.state in ('cancelled', 'draft') and rec.plan_id:
                    # 检查是否还有别的有效排期
                    other = self.search([
                        ('plan_id', '=', rec.plan_id.id),
                        ('state', '=', 'scheduled'),
                        ('id', '!=', rec.id),
                    ], limit=1)
                    if not other:
                        rec.plan_id.scheduled_date = False
        return res

    def unlink(self):
        for rec in self:
            if rec.plan_id:
                other = self.search([
                    ('plan_id', '=', rec.plan_id.id),
                    ('state', '=', 'scheduled'),
                    ('id', '!=', rec.id),
                ], limit=1)
                if not other:
                    rec.plan_id.scheduled_date = False
        return super().unlink()

    # -----------------------------------------------------------
    # 校验：warehouse_transfer 时 source_warehouse 不可空
    # -----------------------------------------------------------
    @api.constrains('plan_id')
    def _check_plan_destination(self):
        for rec in self:
            if rec.plan_id and rec.plan_id.destination_type == 'warehouse_transfer' and not rec.plan_id.source_warehouse_id:
                raise ValidationError(
                    _('Cannot schedule a warehouse transfer plan without a Source Warehouse. '
                      'Please set Source Warehouse on the pick-up plan first.'))

    # -----------------------------------------------------------
    # API 辅助方法（供 controller/calendar JS 调用）
    # -----------------------------------------------------------
    def api_create_schedule(self, plan_id, scheduled_date, container_line_id=None):
        """日历拖拽创建排期（供 JSON API 调用）"""
        plan = self.env['pickup.plan'].browse(plan_id)
        if not plan.exists():
            return {'ok': False, 'error': _('Plan not found')}

        # 校验：仅 plan-driven 场景可排期
        if plan.destination_type not in ('warehouse', 'warehouse_transfer'):
            return {'ok': False, 'error': _('Scheduling is only available for warehouse or warehouse transfer destinations.')}

        # 校验：container 类型必须有 container_line_id
        if plan.cargo_type == 'container' and not container_line_id and not plan.container_line_ids:
            return {'ok': False, 'error': _('No container lines to schedule for this plan.')}

        # 创建排期记录（一个柜一条/托件整个需求一条）
        created = []
        if plan.cargo_type == 'container' and container_line_id:
            # 排指定柜
            existing = self.search([
                ('container_line_id', '=', container_line_id),
                ('scheduled_date', '=', scheduled_date),
            ], limit=1)
            if not existing:
                schedule = self.create({
                    'plan_id': plan_id,
                    'container_line_id': container_line_id,
                    'scheduled_date': scheduled_date,
                    'state': 'scheduled',
                })
                created.append(schedule.id)
        elif plan.cargo_type == 'container' and not container_line_id:
            # 排所有柜
            for cl in plan.container_line_ids:
                existing = self.search([
                    ('container_line_id', '=', cl.id),
                    ('scheduled_date', '=', scheduled_date),
                ], limit=1)
                if not existing:
                    schedule = self.create({
                        'plan_id': plan_id,
                        'container_line_id': cl.id,
                        'scheduled_date': scheduled_date,
                        'state': 'scheduled',
                    })
                    created.append(schedule.id)
        else:
            # 托件：一个需求一个排期
            existing = self.search([
                ('plan_id', '=', plan_id),
                ('scheduled_date', '=', scheduled_date),
                ('container_line_id', '=', False),
            ], limit=1)
            if not existing:
                schedule = self.create({
                    'plan_id': plan_id,
                    'scheduled_date': scheduled_date,
                    'state': 'scheduled',
                })
                created.append(schedule.id)

        return {'ok': True, 'schedule_ids': created}

    def api_delete_schedule(self, schedule_id):
        """日历取消排期（供 JSON API 调用）"""
        schedule = self.browse(schedule_id)
        if not schedule.exists():
            return {'ok': False, 'error': _('Schedule not found.')}
        schedule.action_cancel()
        return {'ok': True}

    def api_get_schedules(self, year, month, destination_id=None):
        """按月获取排期数据（供日历 API 调用）"""
        from datetime import date
        now = date.today()
        year_int = int(year) if year else now.year
        month_int = int(month) if month else now.month

        start_str = '%d-%02d-01' % (year_int, month_int)
        if month_int == 12:
            end_str = '%d-01-01' % (year_int + 1)
        else:
            end_str = '%d-%02d-01' % (year_int, month_int + 1)

        domain = [
            ('scheduled_date', '>=', start_str),
            ('scheduled_date', '<', end_str),
            ('state', '=', 'scheduled'),
        ]
        if destination_id:
            domain.append(('warehouse_id', '=', int(destination_id)))

        schedules = self.search_read(domain, [
            'id', 'plan_id', 'scheduled_date', 'state',
            'container_line_id', 'cargo_type', 'cargo_description',
            'pallet_count', 'cargo_weight',
            'container_number', 'container_type', 'bl_number',
            'warehouse_id', 'display_name',
        ])

        result = {}
        for s in schedules:
            ds = str(s['scheduled_date'])
            if ds not in result:
                result[ds] = {'count': 0, 'schedules': []}
            result[ds]['count'] += 1
            result[ds]['schedules'].append(s)

        return result

    def api_get_unplanned(self, destination_id=None, warehouse_id=None):
        """获取待排期的计划（供日历左侧面板 API 调用）"""
        Plan = self.env['pickup.plan']
        dest_id = destination_id or warehouse_id

        domain = [
            ('scheduled_date', '=', False),
            ('destination_type', 'in', ('warehouse', 'warehouse_transfer')),
        ]
        if dest_id:
            domain.append(('warehouse_id', '=', int(dest_id)))

        plans = Plan.search_read(domain, [
            'id', 'name', 'cargo_type', 'cargo_description',
            'pallet_count', 'package_count', 'cargo_weight', 'cargo_volume',
            'warehouse_id', 'destination_type', 'container_line_ids',
        ])

        result = []
        for p in plans:
            item = {
                'plan_id': p['id'],
                'name': p['name'],
                'cargo_type': p['cargo_type'],
                'cargo_description': p['cargo_description'] or '',
                'pallet_count': p['pallet_count'] or 0,
                'package_count': p['package_count'] or 0,
                'cargo_weight': p['cargo_weight'] or 0,
                'destination_type': p['destination_type'],
                'warehouse': '',
                'containers': [],
            }
            if p['warehouse_id']:
                wh = self.env['stock.warehouse'].browse(p['warehouse_id'][0])
                item['warehouse'] = wh.name

            if p['cargo_type'] == 'container' and p['container_line_ids']:
                for cl_id in p['container_line_ids']:
                    cl = self.env['pickup.plan.container.line'].browse(cl_id)
                    # 检查是否已排期
                    scheduled = self.search([
                        ('container_line_id', '=', cl_id),
                        ('state', '=', 'scheduled'),
                    ], limit=1)
                    item['containers'].append({
                        'id': cl.id,
                        'container_number': cl.container_number,
                        'container_type': cl.container_type,
                        'bl_number': cl.bl_number,
                        'weight': cl.weight,
                        'scheduled': bool(scheduled),
                    })
            result.append(item)

        return result
