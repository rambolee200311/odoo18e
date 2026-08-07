# -*- coding: utf-8 -*-
from odoo import fields, models, _


class WorkflowGuard(models.Model):
    """Configurable workflow guard rule (Sprint50-A)."""

    _name = 'tlmp.workflow.guard'
    _description = 'Workflow Guard Rule'
    _order = 'sequence, id'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    res_model = fields.Char(string='Document Model', required=True, index=True)
    from_state = fields.Char(string='From State', default='*')
    to_state = fields.Char(string='To State', default='*')
    guard_code = fields.Selection([
        ('general', 'General'),
        ('validation_state_passed', 'Validation State Passed'),
        ('quote_customer_approval', 'Quote Customer Approval'),
        ('pod_received', 'POD Received'),
        ('delivery_completed', 'Delivery Completed'),
        ('assignment_context_required', 'Assignment Context Required'),
    ], string='Guard Code', required=True, default='general')
    message = fields.Char(string='Block Message')
    sequence = fields.Integer(string='Sequence', default=100)
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('unique_guard_rule',
         'UNIQUE(res_model, from_state, to_state, guard_code)',
         _('A guard rule with this combination already exists.')),
    ]
