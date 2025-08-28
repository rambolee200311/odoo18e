from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Project(models.Model):
    _inherit = 'project.project'

    category = fields.Many2one('product.category', string='Category', tracking=True)
    owner = fields.Many2one('res.partner', string='Owner', tracking=True)
    inbound_cmr_template_file = fields.Binary(
        string='Template File(Inbound CMR)',
        help='Upload the Excel template file.'
    )
    inbound_cmr_template_file_name = fields.Char(
        string='Template File Name(Inbound CMR)',
        help='The name of the uploaded template file.'
    )
    outbound_cmr_template_file = fields.Binary(
        string='Template File(Outbound CMR)',
        help='Upload the Excel template file.'
    )
    outbound_cmr_template_file_name = fields.Char(
        string='Template File Name(Outbound CMR)',
        help='The name of the uploaded template file.'
    )
'''
    # 港至仓 (Trucking Charge)
    inbound_trucking_charge = fields.Float(
        string='Trucking Charge',
        default=0.0,
        tracking=True
    )

    # 尾程配送 (Last Mile Delivery Charge)
    outbound_delivery_charge = fields.Float(
        string='Delivery Charge',
        default=0.0,
        tracking=True
    )

    # 系统 (System File and Document Admin Fee)
    inbound_system_file_charge = fields.Float(
        string='System File and Document Admin Fee',
        default=10.0,
        tracking=True
    )
    # 系统 (System File and Document Admin Fee)
    outbound_system_file_charge = fields.Float(
        string='System File and Document Admin Fee',
        default=10.0,
        tracking=True
    )

    # 危险品 (Dangerous Goods Declaration Charge)
    inbound_DGD_charge = fields.Float(
        string='Dangerous Goods Declaration Charge',
        default=7.5,
        tracking=True
    )
    # 危险品 (Dangerous Goods Declaration Charge)
    outbound_DGD_charge = fields.Float(
        string='Dangerous Goods Declaration Charge',
        default=7.5,
        tracking=True
    )

    # 入库操作 (Inbound Handling)
    inbound_handling_price = fields.Float(
        string='Handling Price',
        default=0.0,
        tracking=True
    )
    inbound_handling_per = fields.Selection(
        selection=[
            ('pallet', 'Per Pallet'),
            ('piece', 'Per Piece')
        ],
        string='Inbound Handling Per',
        default='pallet',
        required=True
    )

    # 出库操作 (Outbound Handling)
    outbound_handling_price = fields.Float(
        string='Handling Price',
        default=0.0,
        tracking=True
    )
    outbound_handling_per = fields.Selection(
        selection=[
            ('pallet', 'Per Pallet'),
            ('piece', 'Per Piece')
        ],
        string='Inbound Handling Per',
        default='pallet',
        required=True
    )

    # 入库扫描 (Inbound Scanning)
    inbound_scanning_price = fields.Float(
        string='Scanning Price',
        default=0.0,
        tracking=True
    )
    # 出库扫描 (Outbound Scanning)
    outbound_scanning_price = fields.Float(
        string='Scanning Price',
        default=0.0,
        tracking=True
    )
    
    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', tracking=True)
    receipt_operation_type = fields.Many2one('stock.picking.type', string='Receipt Operation Type', tracking=True,
                                             domain="[('warehouse_id', '=', warehouse)]")
    pick_operation_type = fields.Many2one('stock.picking.type', string='Pick Operation Type', tracking=True,
                                          domain="[('warehouse_id', '=', warehouse)]")

    outbound_loading_ids = fields.One2many('project.outbound.loading', 'project_id', string='Outbound Loadings')

    outbound_palletizing_price=fields.Float(string='Palletizing Charge', default=15.0, tracking=True)
    outbound_palle_fba_stamp = fields.Float(string='Euro pallet-FBA Stamp', default=30.0, tracking=True)
    outbound_palle_non_stamp = fields.Float(string='Euro pallet-NON Stamp', default=15.0, tracking=True)
    '''
'''
class ProjectOutboundLoading(models.Model):
    _name = 'project.outbound.loading'
    _description = 'Project Outbound Loading'
    _order = 'weight_range_low'

    project_id = fields.Many2one('project.project', string='Project', required=True, ondelete='cascade')
    weight_range_low = fields.Float(string='Low(KG)', required=True, default=0.0)
    weight_range_high = fields.Float(string='High(KG)', required=True)
    charge = fields.Float(string='Charge', required=True)
    unit = fields.Selection([('pallet', 'Per Pallet'), ('piece', 'Per Piece')], string='Unit', required=True,
                            default='pallet')
    description = fields.Text(string='Description')

    @api.constrains('weight_range_low', 'weight_range_high')
    def _check_weight_range(self):
        for record in self:
            if record.weight_range_low >= record.weight_range_high:
                raise ValidationError("Low weight must be less than High weight.")
            if record.weight_range_low < 0 or record.weight_range_high <= 0:
                raise ValidationError("Weight ranges must be positive.")
            overlapping_ranges = self.search([
                ('project_id', '=', record.project_id.id),
                ('id', '!=', record.id),
                '|',
                '&', ('weight_range_low', '<', record.weight_range_high),
                ('weight_range_high', '>', record.weight_range_low),
                '&', ('weight_range_high', '>', record.weight_range_low),
                ('weight_range_low', '<', record.weight_range_high)
            ])
            if overlapping_ranges:
                raise ValidationError("Weight ranges cannot overlap within the same project.")
'''