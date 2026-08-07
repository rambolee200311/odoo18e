from odoo import api, fields, models, _


class CarrierProfile(models.Model):
    """承运商运输属性扩展 — 一对一挂 res.partner
    不独立创建承运商主数据，res.partner 是身份主实体。
    创建策略：manual 或 on_first_carrier_usage。
    """
    _name = 'tlmp.carrier.profile'
    _description = 'Carrier Profile'
    _rec_name = 'display_name'

    partner_id = fields.Many2one(
        'res.partner', string='Partner',
        required=True,
        domain="[('is_company', '=', True)]",
        help='一对一绑定 res.partner，不独立创建承运商身份')
    carrier_code = fields.Char(
        string='Carrier Code', required=True, copy=False,
        help='承运商代码，如 DHL/UPS/DPD')
    carrier_type = fields.Selection([
        ('truck_fuel', 'Truck (FTL) — Diesel/Fuel'),
        ('truck_road', 'Truck (LTL) — Road'),
        ('express_standard', 'Express — Standard'),
        ('express_express', 'Express — Express'),
        ('_3pl', '3PL (Groupage)'),
    ], string='Category', required=True, default='truck_fuel')
    settlement_mode = fields.Selection([
        ('auto', 'Auto Settlement'),
        ('manual', 'Manual Review'),
    ], string='Settlement Mode', default='auto')
    is_active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name', store=False)

    _sql_constraints = [
        ('carrier_code_company_unique',
         'unique(carrier_code, company_id)',
         'Carrier code must be unique per company.'),
    ]

    @api.depends('partner_id', 'carrier_code')
    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s [%s]' % (r.partner_id.name or '', r.carrier_code or '')

    @api.model
    def _get_or_create(self, partner):
        if not partner:
            return False
        profile = self.search([('partner_id', '=', partner.id)], limit=1)
        if profile:
            return profile
        if not partner.is_company:
            return False
        return self.create({
            'partner_id': partner.id,
            'carrier_code': partner.name[:20].upper().replace(' ', '_'),
            'carrier_type': 'truck_fuel',
        })
