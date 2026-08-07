from odoo import api, fields, models, _


class CarrierMatchRule(models.Model):
    """承运商匹配规则 — 配置层，不承载执行逻辑
    本期仅支持 reference.ref_type + reference.ref_value 结构化条件。
    不做 JSON 规则引擎（延后 Sprint30-B）。
    """
    _name = 'tlmp.carrier.match.rule'
    _description = 'Carrier Match Rule'
    _rec_name = 'name'
    _order = 'sequence, id'

    name = fields.Char(string='Rule Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10, required=True,
                              help='高优先级规则先执行')
    carrier_id = fields.Many2one(
        'res.partner', string='Carrier', optional=True,
        domain="[('is_company', '=', True)]",
        help='规则适用承运商，为空作为全局通用规则')
    match_ref_type = fields.Selection([
        ('pickup_code', 'Pickup Code'),
        ('container_no', 'Container No.'),
        ('tracking_no', 'Tracking No.'),
        ('cmr_no', 'CMR No.'),
        ('bl_no', 'Bill of Lading'),
        ('po_no', 'PO No.'),
        ('delivery_no', 'Delivery No.'),
        ('booking_no', 'Booking No.'),
        ('shipment_no', 'Shipment No.'),
    ], string='Match Ref Type', required=True,
        help='待匹配的 reference.ref_type')
    match_ref_value = fields.Char(
        string='Match Ref Value', required=True,
        help='待匹配的 reference.ref_value')
    min_auto_confirm_score = fields.Float(string='Min Auto Score', default=0.0, help='覆盖全局阈值，0=使用 ir.config_parameter tlms.auto_match.min_score')
    is_active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)


class CarrierMatchSuggestion(models.Model):
    """匹配建议 — 人工确认后才写入 allocation
    核心：candidate_reference (Odoo Reference)，一期仅 transport.order。
    candidate_order_id 为快捷访问字段（compute）。
    """
    _name = 'tlmp.carrier.match.suggestion'
    _description = 'Match Suggestion'
    _rec_name = 'display_name'
    _order = 'create_date desc'

    billing_line_id = fields.Many2one(
        'tlmp.carrier.billing.line', string='Billing Line',
        required=True, ondelete='cascade')
    candidate_reference = fields.Reference(
        selection=[('tlmp.transport.order', 'Transport Order')],
        string='Candidate', required=True,
        help='匹配建议的候选业务对象，一期仅 transport.order')
    candidate_order_id = fields.Many2one(
        'tlmp.transport.order', string='Order',
        compute='_compute_candidate_order', store=False,
        search='_search_candidate_order',
        help='快捷访问字段')
    match_rule_id = fields.Many2one(
        'tlmp.carrier.match.rule', string='Match Rule', optional=True)
    confidence_score = fields.Float(
        string='Confidence', default=0.0,
        help='置信度 0.0-1.0')
    confidence_source = fields.Selection([
        ('bl_exact', 'BL Exact'),
        ('container_exact', 'Container Exact'),
        ('tracking_exact', 'Tracking Exact'),
        ('manual', 'Manual'),
        ('rule_match', 'Rule Match'),
    ], string='Confidence Source', required=True)
    state = fields.Selection([
        ('draft', 'Pending Review'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ], string='Status', default='draft', required=True)
    execution_id = fields.Many2one('tlmp.carrier.match.execution', string='Execution')
    operator = fields.Many2one('res.users', string='Operator')
    create_date = fields.Datetime(string='Created', default=fields.Datetime.now)

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name', store=False)

    _sql_constraints = [
        ('unique_billing_line_candidate',
         'unique(billing_line_id, match_rule_id)',
         'This suggestion already exists for this billing line under this rule.'),
    ]

    @api.depends('candidate_reference')
    def _compute_candidate_order(self):
        for r in self:
            if r.candidate_reference and r.candidate_reference._name == 'tlmp.transport.order':
                r.candidate_order_id = r.candidate_reference.id
            else:
                r.candidate_order_id = False

    def _search_candidate_order(self, operator, value):
        return [('candidate_order_id', operator, value)]

    @api.depends('candidate_reference')
    def _compute_display_name(self):
        for r in self:
            ref_display = str(r.candidate_reference) if r.candidate_reference else ''
            r.display_name = 'Suggestion: %s' % ref_display

    def action_confirm(self):
        for r in self:
            r.write({'state': 'confirmed', 'operator': self.env.uid})
            self.env['tlmp.carrier.matching.history'].create({
                'billing_line_id': r.billing_line_id.id,
                'transport_order_id': r.candidate_order_id.id,
                'match_rule_id': r.match_rule_id.id,
                'suggestion_id': r.id,
                'operation': 'suggestion_confirmed',
                'from_state': 'draft',
                'to_state': 'confirmed',
                'operator': self.env.uid,
            })
        return True

    def action_reject(self):
        for r in self:
            r.write({'state': 'rejected', 'operator': self.env.uid})
            self.env['tlmp.carrier.matching.history'].create({
                'billing_line_id': r.billing_line_id.id,
                'transport_order_id': r.candidate_order_id.id,
                'match_rule_id': r.match_rule_id.id,
                'suggestion_id': r.id,
                'operation': 'suggestion_rejected',
                'from_state': 'draft',
                'to_state': 'rejected',
                'operator': self.env.uid,
            })
        return True


class CarrierMatchingHistory(models.Model):
    """匹配操作审计日志"""
    _name = 'tlmp.carrier.matching.history'
    _description = 'Matching History'
    _order = 'change_date desc'

    billing_line_id = fields.Many2one(
        'tlmp.carrier.billing.line', string='Billing Line')
    transport_order_id = fields.Many2one(
        'tlmp.transport.order', string='Transport Order')
    match_rule_id = fields.Many2one(
        'tlmp.carrier.match.rule', string='Match Rule')
    suggestion_id = fields.Many2one(
        'tlmp.carrier.match.suggestion', string='Suggestion')
    operation = fields.Selection([
        ('suggestion_created', 'Suggestion Created'),
        ('suggestion_confirmed', 'Confirmed'),
        ('suggestion_rejected', 'Rejected'),
        ('allocation_created', 'Allocation Created'),
        ('allocation_reversed', 'Allocation Reversed'),
    ], string='Operation', required=True)
    from_state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
    ], string='From State')
    to_state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
    ], string='To State')
    execution_id = fields.Many2one('tlmp.carrier.match.execution', string='Execution')
    operator = fields.Many2one('res.users', string='Operator')
    change_date = fields.Datetime(
        string='Change Date', default=fields.Datetime.now)
    execution_id = fields.Many2one('tlmp.carrier.match.execution', string='Execution')
    error_message = fields.Text(string='Error Message')
    allocation_id = fields.Many2one('tlmp.carrier.settlement.allocation', string='Allocation')
    note = fields.Text(string='Note')
