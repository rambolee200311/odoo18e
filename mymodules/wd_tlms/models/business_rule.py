from odoo import models, fields


class BusinessRule(models.Model):
    _name = 'tlmp.business.rule'
    _description = 'Business Matrix Rule'
    _rec_name = 'name'
    _order = 'priority, id'

    code = fields.Char(string='Rule Code', required=True)
    name = fields.Char(string='Rule Name', required=True)
    message_cn = fields.Char(string='Message (CN)', required=True)
    result = fields.Selection([
        ('block', 'BLOCK'),
        ('warning', 'WARNING'),
    ], string='Result', default='block', required=True)
    priority = fields.Integer(string='Priority', default=100)
    cargo_category = fields.Selection([
        ('container', 'C1 Container'),
        ('pallet', 'C2 Pallet'),
        ('piece', 'C3 Piece'),
    ], string='Cargo Category')
    carrier_type = fields.Selection([
        ('own_fleet', 'D1 Own Fleet'),
        ('truck', 'D2 Third-Party Truck'),
        ('courier', 'D3 Courier'),
    ], string='Carrier Type')
    t1_attribute = fields.Selection([
        ('t1', 'E1 T1'),
        ('normal', 'E2 Normal'),
    ], string='T1 Attribute')
    dg_attribute = fields.Selection([
        ('dg', 'F1 Dangerous'),
        ('normal', 'F2 Normal'),
    ], string='DG Attribute')
    require_capability = fields.Char(
        string='Require Carrier Capability',
        help='Rule blocks only when the carrier lacks this capability '
             '(e.g. t1 / dg). Empty = capability not considered.')
    apply_mixed_root = fields.Boolean(
        string='Block Mixed Cargo Roots',
        help='RULE-CARGO-005: single request must have a single Cargo Category root.')
    vehicle_policy_mode = fields.Selection([
        ('required', 'Required'),
        ('exempted', 'Exempted'),
    ], string='Vehicle Policy Mode',
        help='carrier_type_vehicle_policy: whether vehicle requirement rules apply for this carrier_type.')
    vehicle_body_type = fields.Selection([
        ('no_requirement', 'No Requirement'),
        ('rear_only', 'Rear Only'),
        ('side_loading', 'Side Loading'),
        ('side_rear_both', 'Side & Rear'),
        ('top_loading', 'Top Loading'),
        ('tail_lift', 'Tail Lift'),
        ('open_flatbed', 'Open Flatbed'),
        ('reefer_refrigerated', 'Reefer'),
        ('tanker', 'Tanker'),
    ], string='Vehicle Body Type Constraint',
        help='Vehicle body type required by this rule (RULE-VEHICLE-005).')
    vehicle_capacity_requirement = fields.Selection([
        ('no_limit', 'No Limit'),
        ('below_40t', '< 40t'),
        ('40t_44t', '40t-44t'),
        ('over_44t', '> 44t'),
    ], string='Vehicle Capacity Requirement',
        help='Minimum vehicle capacity required by this rule (RULE-VEHICLE-003).')
    active = fields.Boolean(string='Active', default=True)
