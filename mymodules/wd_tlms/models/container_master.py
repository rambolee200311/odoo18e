# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ContainerMaster(models.Model):
    _name = 'container.master'
    _description = 'Container Master Record'
    _order = 'container_number'
    _rec_name = 'container_number'

    container_number = fields.Char(string='Container No.', required=True, index=True)
    container_type = fields.Selection([
        ('20GP', '20GP'), ('40GP', '40GP'), ('40HQ', '40HQ'),
        ('40HC', '40HC'), ('45HQ', '45HQ'), ('OT', 'OT'),
        ('FR', 'FR'), ('RF', 'RF'), ('other', 'Other'),
    ], string='Container Type', required=True)
    owner_id = fields.Many2one('res.partner', string='Container Owner',
                               help='Shipping line or leasing company')
    current_location_id = fields.Many2one('res.partner', string='Current Location')
    current_status = fields.Selection([
        ('loaded', 'Loaded (with cargo)'),
        ('empty', 'Empty at warehouse'),
        ('at_depot', 'At depot/terminal'),
        ('with_carrier', 'With carrier'),
        ('damaged', 'Damaged'),
    ], string='Current Status', default='at_depot')
    last_service_date = fields.Date(string='Last Service Date')
    last_visit_date = fields.Date(
        string='Last Visit Date',
        compute='_compute_visit_stats', store=True)
    total_visits = fields.Integer(
        string='Total Visits',
        compute='_compute_visit_stats', store=True)

    history_line_ids = fields.One2many(
        'container.master.history.line', 'master_id',
        string='Container History', readonly=True)
    notes = fields.Text(string='Notes')
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('container_number_uniq', 'unique(container_number)',
         'Container number must be unique!'),
    ]

    @api.model
    def find_or_create(self, container_number, container_type=None, defaults=None):
        """
        Find an existing master record by container number, or create a new one.
        If found and archived, reactivate and update visit tracking.
        Returns (record, created_bool).
        """
        ContainerMaster = self.env['container.master']
        number = (container_number or '').strip().upper()
        if not number:
            return (self.env['container.master'], False)

        existing = ContainerMaster.search([('container_number', '=', number)], limit=1)
        if existing:
            existing.write({'active': True})
            return (existing, False)

        vals = {
            'container_number': number,
            'container_type': container_type or '20GP',
            'active': True,
        }
        if defaults:
            vals.update(defaults)
        new_master = ContainerMaster.create(vals)
        self.env['container.master.history.line'].create({
            'master_id': new_master.id,
            'reference_type': 'pickup_plan',
            'direction': 'inbound',
            'remark': 'Auto-created via find_or_create',
        })
        return (new_master, True)

    @api.depends('history_line_ids', 'history_line_ids.master_id')
    def _compute_visit_stats(self):
        for rec in self:
            lines = rec.history_line_ids.sorted('id', reverse=True)
            rec.last_visit_date = lines[0].create_date.date() if lines else False
            rec.total_visits = len(lines)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('container_number'):
                vals['container_number'] = vals['container_number'].strip().upper()
        return super().create(vals_list)




class ContainerMasterHistoryLine(models.Model):
    _name = 'container.master.history.line'
    _description = 'Container History'
    _order = 'id desc'

    master_id = fields.Many2one(
        'container.master', string='Container',
        required=True, ondelete='cascade', index=True)
    reference_type = fields.Selection([
        ('pickup_plan', 'Pickup Plan'),
        ('transport_order', 'Transport Order'),
        ('container_service_request', 'Container Service Request'),
    ], string='Source Type', required=True, index=True)
    reference_id = fields.Integer(
        string='Source ID',
        help='ID of the source document for traceability')
    bl_number = fields.Char(string='BL No.', index=True)
    eta = fields.Date(string='ETA')
    ata = fields.Date(string='ATA')
    inbound_date = fields.Date(string='Inbound Date')
    return_date = fields.Date(string='Return Date')
    direction = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ], string='Direction', required=True, default='inbound',
        help='Inbound = entering our system. Outbound = leaving.')
    location_start = fields.Char(string='From Location')
    location_end = fields.Char(string='To Location')
    remark = fields.Text(string='Remark')
