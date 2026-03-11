from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class AccountPayment(models.Model):
    _inherit = "account.payment"


    # def action_validate(self):
    #     for rec in self:
    #         if rec.partner_type == "customer":
    #             if  not rec.attachment_ids:
    #                 raise ValidationError(_("Bank proof attachment is required before posting payment."))
    #     return super().action_validate()