from odoo import fields, models, _

class ResPartnerInherit(models.Model):
    _inherit = "res.partner"

    eu_eori_no = fields.Char(string="EORI No")
    #vat_tax_no = fields.Char(string="VAT No")

    is_shipping_line = fields.Boolean(string="Shipping Line", index=True)
    is_exporter = fields.Boolean(string="Exporter", index=True)
    is_importer = fields.Boolean(string="Importer", index=True)
    is_customs_broker = fields.Boolean(string="Customs Broker", index=True)
    is_notify_party = fields.Boolean(string="Notify Party", index=True)
    is_payment = fields.Boolean(string="Payment Company", index=True)
    is_receipt = fields.Boolean(string="Receipt Company", index=True)