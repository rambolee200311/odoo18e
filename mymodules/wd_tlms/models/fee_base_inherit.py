from odoo import models, fields


class TransportQuote(models.Model):
    _inherit = 'tlmp.transport.quote'

    fee_line_ids = fields.One2many(
        'transport.fee.line', 'source_quote_id',
        string='Fee Lines', copy=False,
        help='Fee line items for this quote (commercial flow).')


class TransportOrder(models.Model):
    _inherit = 'tlmp.transport.order'

    fee_line_ids = fields.One2many(
        'transport.fee.line', 'source_order_id',
        string='Fee Lines', copy=False,
        help='Fee line items for this order (final fee calculation).')
