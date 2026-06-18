from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class StockLocationType(models.Model):
    _name = 'stock.location.type'
    _description = 'Stock Location Type'
    _rec_name = 'name'

    code = fields.Char(string='Code')
    name = fields.Char(string='Name')
    description = fields.Text(string='Description')

    @api.constrains('code', 'name')
    def _check_code_name_unique(self):
        for record in self:
            if record.code:
                existing_code = self.search([('code', '=', record.code), ('id', '!=', record.id)])
                if existing_code:
                    raise ValidationError(_('Location Type code "%s" must be unique.') % record.code)
            if record.name:
                existing_name = self.search([('name', '=', record.name), ('id', '!=', record.id)])
                if existing_name:
                    raise ValidationError(_('Location Type name "%s" must be unique.') % record.name)