import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'
    _sql_constraints = [('barcode_unique', 'unique(barcode)', 'Barcode must be unique.')]

    barcode = fields.Char(string='Barcode', copy=False, index=True)
    billno = fields.Char(string='Bill No', copy=False)
    reference = fields.Char(string='Reference', copy=False)
    cntr_no = fields.Char(string='Container No', copy=False)
    original_pallet_no = fields.Char(string='Original Pallet No', copy=False, index=True)
    lifecycle_state = fields.Selection([('active', 'Active'), ('consumed', 'Consumed'), ('closed', 'Closed')], string='Lifecycle State', readonly=True, copy=False, index=True)
    lifecycle_start_datetime = fields.Datetime(string='Lifecycle Start At', readonly=True, copy=False, index=True)
    consumed_datetime = fields.Datetime(string='Consumed At', readonly=True, copy=False, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if not vals.get('barcode'):
                vals['barcode'] = self.generate_package_barcode()
        return super().create(vals_list)

    @api.model
    def generate_package_barcode(self):
        for _attempt in range(20):
            barcode = uuid.uuid4().hex[:8].upper()
            if not self.sudo().search([('barcode', '=', barcode)], limit=1):
                return barcode
        raise UserError(_('Could not generate a unique Sunrise package barcode.'))
