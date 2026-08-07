from odoo import api, fields, models, _


class TransportReference(models.Model):
    """物流业务引用索引模型 - Transport Reference Index
    定位：IFFM/OMS/TLMS 三系统松耦合的业务引用索引层
    原则：
    - 不承载业务状态和生命周期
    - 同一 ref_value 允许多条记录（container_no 等设备编号跨运输合法）
    - 核心关联使用 res_model + res_id（Char+Integer），不绑定固定 Many2one
    - Odoo Reference 保留仅作为弱关联（UI 跨模型跳转），不作为业务逻辑主键
    """
    _name = 'tlmp.transport.reference'
    _description = 'Transport Reference Index'
    _rec_name = 'display_name'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference Name')
    ref_type = fields.Selection([
        ('pickup_code', 'Pickup Code'),
        ('container_no', 'Container No.'),
        ('tracking_no', 'Tracking No.'),
        ('cmr_no', 'CMR No.'),
        ('bl_no', 'Bill of Lading'),
        ('po_no', 'PO No.'),
        ('delivery_no', 'Delivery No.'),
        ('booking_no', 'Booking No.'),
        ('shipment_no', 'Shipment No.'),
        ('other', 'Other'),
    ], string='Reference Type', required=True)
    ref_value = fields.Char(string='Reference Value', required=True, index=True)
    reference_role = fields.Selection([
        ('identifier', 'Identifier'),
        ('equipment', 'Equipment'),
        ('document', 'Document'),
        ('external', 'External'),
    ], string='Role', default='identifier', required=True)
    source_system = fields.Selection([
        ('iff', 'IFFM'),
        ('oms', 'OMS'),
        ('tlms', 'TLMS'),
        ('external', 'External'),
    ], string='Source System', default='tlms', required=True)

    # 核心关联：res_model + res_id（跨系统通用，不绑定固定 Many2one）
    res_model = fields.Char(string='Linked Model', index=True)
    res_id = fields.Integer(string='Linked Record ID')

    # Odoo Reference 弱关联（仅用于 UI 跨模型跳转，不作业务逻辑主键）
    reference = fields.Reference(
        selection=[], string='Linked Document',
        help='Weak association for UI cross-model navigation only.')

    # 扩展字段
    partner_id = fields.Many2one('res.partner', string='Partner')
    reference_scope = fields.Selection([
        ('shipment', 'Shipment'),
        ('transport', 'Transport'),
        ('billing', 'Billing'),
    ], string='Scope', help='匹配优先级: BL > Container+date > Tracking > Pickup')
    valid_from = fields.Date(string='Valid From')
    valid_to = fields.Date(string='Valid To')
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    date = fields.Date(string='Date', default=fields.Date.today)

    # Display
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name', store=False)

    _sql_constraints = [
        ('check_ref_value_not_empty',
         "check(ref_value != '')",
         'Reference value cannot be empty.'),
        ('unique_ref_object',
         'unique(ref_type, ref_value, res_model, res_id)',
         '同一对象不能重复挂相同引用（不同对象可挂相同 ref_value）。'),
    ]
    # 注意：不对 (ref_type, ref_value) 添加唯一约束
    # container_no/bl_no/tracking_no 等业务编号天然可重复（跨运输、跨航次）
    # 同一 ref_value 允许多条记录存在

    @api.depends('ref_type', 'ref_value')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s: %s' % (r.ref_type or '', r.ref_value or '')

    @api.model
    def create_for_order(self, order, ref_type='shipment_no'):
        """Auto-create reference record for transport order."""
        return self.create({
            'name': _('Order %s') % order.name,
            'ref_type': ref_type,
            'ref_value': order.name,
            'reference_role': 'identifier',
            'source_system': 'tlms',
            'res_model': 'tlmp.transport.order',
            'res_id': order.id,
            'partner_id': order.partner_id.id or False,
        })

    def action_open_linked_document(self):
        """Open the linked document via res_model + res_id."""
        self.ensure_one()
        if self.res_model and self.res_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': self.res_model,
                'res_id': self.res_id,
                'view_mode': 'form',
                'target': 'current',
            }
        return True

    @api.model
    def search_by_ref(self, ref_type, ref_value):
        """Search references by type and value (allow duplicates)."""
        return self.search([('ref_type', '=', ref_type), ('ref_value', '=', ref_value)])
