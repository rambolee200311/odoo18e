# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class TransportShipmentLabel(models.Model):
    _name = 'tlmp.transport.shipment.label'
    _description = 'Shipment Label - Parcel/LTL/Groupage'
    _rec_name = 'name'
    _order = 'sequence, id'

    name = fields.Char(string='Reference', required=True, copy=False,
                       default=lambda self: _('New'))
    order_id = fields.Many2one('tlmp.transport.order', string='Transport Order',
                               required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)

    # Carrier service (from Sprint24 carrier.service master data)
    carrier_service_id = fields.Many2one(
        'tlmp.carrier.service', string='Carrier Service')

    # Tracking
    tracking_number = fields.Char(string='Tracking Number', index=True)
    carrier_tracking_url = fields.Char(
        string='Tracking URL',
        help='Full URL to carrier tracking page')
    label_pdf = fields.Binary(
        string='Label PDF', attachment=True,
        help='Upload the carrier label PDF')

    # State machine
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('printed', 'Printed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    notes = fields.Text(string='Notes')

    # Auto-sequence
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'tlmp.shipment.label.seq') or _('New')
        return super().create(vals_list)

    # State transition actions
    def action_generate(self):
        for r in self:
            if r.state != 'draft':
                raise UserError(_('Only draft labels can be generated.'))
        self.write({'state': 'generated'})

    def action_print(self):
        for r in self:
            if r.state not in ('generated', 'printed'):
                raise UserError(_('Only generated labels can be printed.'))
        # Download the label PDF
        self.write({'state': 'printed'})
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/label_pdf/%s' % (
                'tlmp.transport.shipment.label', self.id, 'label.pdf'),
            'target': 'new',
        }

    def action_cancel(self):
        for r in self:
            if r.state in ('cancelled',):
                raise UserError(_('Label is already cancelled.'))
            if r.state == 'printed':
                raise UserError(_('Printed labels cannot be cancelled.'))
        self.write({'state': 'cancelled'})

    # Batch print
    def action_print_batch(self):
        labels = self.filtered(lambda l: l.state in ('generated', 'printed'))
        if not labels:
            raise UserError(_('No printable labels selected.'))
        for label in labels:
            if label.state == 'generated':
                label.write({'state': 'printed'})
        # Return first label for download
        return labels[0].action_print()
