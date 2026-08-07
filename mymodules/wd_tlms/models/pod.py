from odoo import models, fields, api, _
from odoo.exceptions import UserError


class Pod(models.Model):
    _name = 'tlmp.pod'
    _description = 'Proof of Delivery'
    _rec_name = 'name'

    name = fields.Char(string='POD No.', required=True, copy=False,
                       default=lambda self: _('New'))
    order_id = fields.Many2one('tlmp.transport.order', string='Transport Order',
                               required=True)
    cmr_id = fields.Many2one('tlmp.cmr', string='CMR')
    signed_by = fields.Char(string='Signed By')
    signature_image = fields.Binary(string='Signature', attachment=True)
    signed_date = fields.Datetime(string='Signed Date')
    delivery_photo_ids = fields.Many2many('ir.attachment', string='Delivery Photos')
    goods_condition = fields.Selection([
        ('intact', 'Intact'),
        ('damaged', 'Damaged'),
        ('short', 'Short'),
        ('rejected', 'Rejected'),
    ], string='Goods Condition', default='intact')
    damage_description = fields.Text(string='Damage Description')
    customer_notified = fields.Boolean(string='Customer Notified', default=False)
    customer_confirm_date = fields.Datetime(string='Customer Confirm Date')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('disputed', 'Disputed'),
    ], string='Status', default='pending')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tlmp.pod.seq') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        self.order_id.action_confirm_pod()
        return True

    def action_dispute(self):
        self.write({'state': 'disputed'})
        return True
