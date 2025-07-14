from odoo import models, fields


class Project(models.Model):
    _inherit = 'project.project'

    # 港至仓 (Trucking Charge)
    inbound_trucking_charge = fields.Float(
        string='Trucking Charge',
        default=0.0,
        tracking=True
    )

    # 系统 (System File and Document Admin Fee)
    inbound_system_file_charge = fields.Float(
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

    # 入库扫描 (Inbound Scanning)
    inbound_scanning_price = fields.Float(
        string='Scanning Price',
        default=0.0,
        tracking=True
    )
    owner = fields.Many2one('res.partner', string='Owner', tracking=True)
