from odoo import fields, models, _

class ResPartnerInherit(models.Model):
    _inherit = "res.partner"

    eu_eori_no = fields.Char(string="EORI No")
    vat_tax_no = fields.Char(string="VAT No")