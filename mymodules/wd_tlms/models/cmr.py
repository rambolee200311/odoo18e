# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class CMR(models.Model):
    _name = 'tlmp.cmr'
    _description = 'CMR Waybill'
    _rec_name = 'name'
    _order = 'id desc'

    # ── Identification ──────────────────────────────────────
    name = fields.Char(string='Reference', required=True, copy=False,
                       default=lambda self: _('New'))
    cmr_number = fields.Char(string='CMR Number', required=True, index=True, copy=False)
    order_id = fields.Many2one('tlmp.transport.order', string='Transport Order',
                               required=True, index=True)
    copy_number = fields.Selection([
        ('1', 'Copy 1 - Sender'),
        ('2', 'Copy 2 - Carrier'),
        ('3', 'Copy 3 - Consignee'),
        ('4', 'Copy 4 - Extra'),
    ], string='Copy', required=True, default='1')

    # ── Line details (cargo lines, replaces old flat fields) ─
    line_ids = fields.One2many('tlmp.cmr.line', 'cmr_id', string='Cargo Lines',
                               copy=True)

    packages_count = fields.Float(
        string='Total Pallets',
        compute='_compute_from_lines', store=True,
        help='Total pallets summed from cargo lines')
    gross_weight = fields.Float(
        string='Gross Weight (kg)',
        compute='_compute_from_lines', store=True,
        help='Total gross weight summed from cargo lines')

    cargo_description = fields.Text(string='Cargo Description (override)')
    container_no = fields.Char(string='Container No.')
    seal_no = fields.Char(string='Seal No.')

    # ── Parties ─────────────────────────────────────────────
    sender_id = fields.Many2one('res.partner', string='Sender', required=True)
    consignee_id = fields.Many2one('res.partner', string='Consignee', required=True)
    carrier_id = fields.Many2one('res.partner', string='Carrier', required=True)
    place_of_taking_over = fields.Char(string='Place of Taking Over')
    place_of_delivery = fields.Char(string='Place of Delivery')
    transit_countries = fields.Char(string='Transit Countries')

    # ── Vehicle ─────────────────────────────────────────────
    vehicle_reg_no = fields.Char(string='Vehicle Reg. No.')

    # ── ADR – related from transport order ──────────────────
    has_dangerous_goods = fields.Boolean(related='order_id.has_dangerous_goods',
                                         readonly=True, string='DG')
    adr_class = fields.Char(related='order_id.adr_class',
                            readonly=True, string='ADR Class')
    adr_un_number = fields.Char(related='order_id.adr_un_number',
                                readonly=True, string='UN No.')

    # ── Financial ───────────────────────────────────────────
    freight_charges = fields.Monetary(string='Freight Charges')
    additional_charges = fields.Monetary(string='Additional Charges')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.company.currency_id)

    # ── Remarks & Instructions ──────────────────────────────
    sender_remarks = fields.Text(string='Sender Remarks')
    carrier_remarks = fields.Text(string='Carrier Remarks')
    sender_instructions = fields.Text(string='Sender Instructions')
    documents_attached = fields.Text(string='Documents Attached')
    dock_number = fields.Char(string='Dock No.')

    # ── Dates ───────────────────────────────────────────────
    pickup_datetime = fields.Datetime(string='Pickup Date')
    delivery_datetime = fields.Datetime(string='Delivery Date')

    # ── Signature / POD ─────────────────────────────────────
    damage_description = fields.Text(string='Reservations / Damage Description')
    signed_by = fields.Char(string='Signed By')
    signed_date = fields.Datetime(string='Signed Date')
    signature_image = fields.Binary(string='Signature', attachment=True)
    signed_cmr_pdf = fields.Binary(string='Signed CMR PDF', attachment=True)
    is_pod_confirmed = fields.Boolean(string='POD Confirmed', default=False)

    # ── Language ────────────────────────────────────────────
    language = fields.Selection([
        ('en', 'English'),
        ('nl', 'Nederlands'),
    ], string='Language', default='en')

    # ── State ───────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('printed', 'Printed'),
        ('in_transit', 'In Transit'),
        ('signed', 'Signed'),
        ('archived', 'Archived'),
    ], string='Status', default='draft')

    # ── SQL constraints ─────────────────────────────────────
    _sql_constraints = [
        ('cmr_copy_unique', 'UNIQUE(cmr_number, copy_number)',
         _('CMR number + copy must be unique!')),
    ]

    # ── Computed totals from lines ──────────────────────────
    @api.depends('line_ids.qty', 'line_ids.gross_weight')
    def _compute_from_lines(self):
        for cmr in self:
            lines = cmr.line_ids
            cmr.packages_count = sum(lines.mapped('qty'))
            cmr.gross_weight = sum(lines.mapped('gross_weight'))

    # ── Auto-sequence ───────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('tlmp.cmr.seq') or _('New')
        return super().create(vals_list)

    # ── Constrains ──────────────────────────────────────────
    @api.constrains('line_ids', 'packages_count', 'gross_weight')
    def _check_cmr_lines(self):
        for cmr in self:
            lines = cmr.line_ids
            if not lines:
                continue
            # Validate total pallets = sum of line qty
            computed_pallets = sum(lines.mapped('qty'))
            if abs(computed_pallets - cmr.packages_count) > 0.01:
                raise ValidationError(_(
                    'Total pallets (%s) does not match the sum of line quantities (%s).'
                ) % (cmr.packages_count, computed_pallets))

            # Validate total gross weight = sum of line gross_weight
            computed_gw = sum(lines.mapped('gross_weight'))
            if abs(computed_gw - cmr.gross_weight) > 0.01:
                raise ValidationError(_(
                    'Total gross weight (%s kg) does not match the sum of line weights (%s kg).'
                ) % (cmr.gross_weight, computed_gw))

    # ── Actions ─────────────────────────────────────────────
    def action_print_cmr(self):
        return self.env.ref('wd_tlms.report_cmr').report_action(self)

    def action_confirm_signature(self):
        self.write({'state': 'signed', 'is_pod_confirmed': True})
        return True

    def action_archive(self):
        self.write({'state': 'archived'})
        return True

    @api.model
    def action_create_from_order(self):
        """Open a CMR form pre-filled from the selected transport order."""
        action = self.env['ir.actions.act_window']._for_xml_id('wd_tlms.action_tlmp_cmr')
        ctx = dict(self.env.context or {})
        order_id = ctx.get('active_id') or ctx.get('default_order_id')
        if not order_id:
            raise UserError(_('Please select a transport order first.'))

        order = self.env['tlmp.transport.order'].browse(order_id)
        if not order.exists():
            raise UserError(_('Transport order not found.'))

        # Sprint20: check for existing CMR to prevent duplicate cargo sync
        existing_cmr = self.search([('order_id', '=', order.id)], limit=1)
        if existing_cmr and not ctx.get('force_new'):
            cargo_exists = self.env['tlmp.cmr.line'].search([
                ('cmr_id', '=', existing_cmr.id),
            ], limit=1)
            if cargo_exists:
                raise UserError(_(
                    'CMR already exists for this order with cargo lines. '
                    'Use "force_new" context to override.'
                ))

        pickup_addr = order.pickup_location_id
        delivery_addr = order.delivery_location_id
        place_taking = pickup_addr.display_name if pickup_addr else ''
        place_delivery = delivery_addr.display_name if delivery_addr else ''

        defaults = {
            'order_id': order.id,
            'sender_id': pickup_addr.id if pickup_addr else False,
            'consignee_id': delivery_addr.id if delivery_addr else False,
            'carrier_id': order.carrier_id.id if order.carrier_id else False,
            'place_of_taking_over': place_taking,
            'place_of_delivery': place_delivery,
            'pickup_datetime': order.planned_pickup_date,
            'delivery_datetime': order.planned_delivery_date,
        }
        action['context'] = dict(ctx, **defaults)
        return action

    @api.model
    def create_cmr_with_cargo(self, order):
        """Create CMR and sync cargo lines from transport order.
        Returns the created CMR record."""
        existing = self.search([('order_id', '=', order.id)], limit=1)
        if existing:
            return existing
        CMR = self.create({
            'order_id': order.id,
            'cmr_number': order.name or self.env['ir.sequence'].next_by_code('tlmp.cmr.seq'),
            'sender_id': order.pickup_location_id.id or order.partner_id.id,
            'consignee_id': order.delivery_location_id.id or False,
            'carrier_id': order.carrier_id.id or False,
            'copy_number': '1',
            'place_of_taking_over': order.pickup_location_id.display_name or '',
            'place_of_delivery': order.delivery_location_id.display_name or '',
        })
        # Copy cargo lines → cmr lines
        CMRL = self.env['tlmp.cmr.line']
        for cl in order.cargo_line_ids:
            existing_line = CMRL.search([
                ('cmr_id', '=', CMR.id),
                ('source_cargo_line_id', '=', cl.id),
            ], limit=1)
            if existing_line:
                continue
            CMRL.create({
                'cmr_id': CMR.id,
                'source_cargo_line_id': cl.id,
                'commodity': cl.description or cl.commodity or '',
                'qty': cl.qty or 0,
                'gross_weight': cl.gross_weight or 0,
                'gross_weight_per_unit': (cl.gross_weight / cl.qty) if cl.qty and cl.gross_weight else 0,
            })
        return CMR
    # ── PDF overlay helpers ──────────────────────────────
    def _get_cmr_field_values(self):
        """Return dict mapping field_identifier → display value for PDF overlay."""
        self.ensure_one()
        vals = {
            'cmr_number': self.cmr_number or '',
            'cmr_ref': self.name or '',
            'order_ref': self.order_id.name or '',
            'sender_name': self.sender_id.display_name or '',
            'sender_street': self.sender_id.street or '',
            'sender_zip_city': '%s %s' % (self.sender_id.zip or '', self.sender_id.city or ''),
            'sender_country': self.sender_id.country_id.name or '',
            'consignee_name': self.consignee_id.display_name or '',
            'consignee_street': self.consignee_id.street or '',
            'consignee_zip_city': '%s %s' % (self.consignee_id.zip or '', self.consignee_id.city or ''),
            'consignee_country': self.consignee_id.country_id.name or '',
            'place_taking': self.place_of_taking_over or '',
            'place_delivery': self.place_of_delivery or '',
            'transit_countries': self.transit_countries or '',
            'carrier_name': self.carrier_id.display_name or '',
            'carrier_street': self.carrier_id.street or '',
            'carrier_zip_city': '%s %s' % (self.carrier_id.zip or '', self.carrier_id.city or ''),
            'carrier_country': self.carrier_id.country_id.name or '',
            'vehicle_reg': self.vehicle_reg_no or '',
            'dock_no': self.dock_number or '',
            'pickup_date': (self.pickup_datetime.strftime('%d/%m/%Y') if self.pickup_datetime else ''),
            'delivery_date': (self.delivery_datetime.strftime('%d/%m/%Y') if self.delivery_datetime else ''),
            'cargo_description': self.cargo_description or '',
            'container_no': self.container_no or '',
            'seal_no': self.seal_no or '',
            'total_pallets': str(self.packages_count or 0),
            'total_gross_weight': '%.1f' % (self.gross_weight or 0.0),
            'total_points': str(sum(self.line_ids.mapped('points')) or 0),
            'sender_remarks': self.sender_remarks or '',
            'carrier_remarks': self.carrier_remarks or '',
            'sender_instructions': self.sender_instructions or '',
            'documents_attached': self.documents_attached or '',
            'freight_charges': '%.2f' % (self.freight_charges or 0.0),
            'additional_charges': '%.2f' % (self.additional_charges or 0.0),
            'has_dg': _('YES') if self.has_dangerous_goods else '',
            'adr_un_no': self.adr_un_number or '',
            'adr_class': self.adr_class or '',
        }
        # Add cargo line fields: line_{idx}_{field}
        for idx, line in enumerate(self.line_ids, start=1):
            prefix = 'line_%d_' % idx
            vals.update({
                prefix + 'commodity': line.commodity or '',
                prefix + 'sku': line.sku or '',
                prefix + 'qty': str(line.qty or 0),
                prefix + 'gw_unit': ('%.1f' % line.gross_weight_per_unit) if line.gross_weight_per_unit else '',
                prefix + 'gw': ('%.1f' % line.gross_weight) if line.gross_weight else '',
                prefix + 'points': str(line.points or 0),
            })
        return vals

    def _get_print_blocks(self):
        """Return list of {x_mm, y_mm, text, font_size, alignment} for PDF overlay."""
        self.ensure_one()
        coords = self.env['tlmp.cmr.coordinate'].search([('active', '=', True)])
        if not coords:
            return []
        field_vals = self._get_cmr_field_values()
        blocks = []
        for c in coords:
            value = field_vals.get(c.field_identifier, '')
            if value:
                blocks.append({
                    'x_mm': c.x_mm,
                    'y_mm': c.y_mm,
                    'text': value,
                    'font_size': c.font_size or 10,
                    'alignment': c.alignment or 'left',
                })
        blocks.sort(key=lambda b: (b['y_mm'], b['x_mm']))
        return blocks
