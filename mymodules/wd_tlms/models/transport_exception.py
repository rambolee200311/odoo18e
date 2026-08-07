# -*- coding: utf-8 -*-
from odoo import models, fields


class TransportExceptionDashboard(models.Model):
    _inherit = 'tlmp.transport.exception'

    timeout_hours = fields.Float(
        string='Timeout (hours)', default=24,
        help='Hours after creation before this exception is considered overdue. '
             'Overrides: driver_delay=4, document_missing=24, cargo_damage=72, customs=168')
