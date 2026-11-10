# -*- coding: utf-8 -*-
from odoo import api, fields, models


class BondedInboundPalletGroup(models.Model):
    _name = 'bonded.inbound.pallet.group'
    _description = 'Bonded Inbound Identical Pallet Group'
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(string='Pallet Group', compute='_compute_name', store=True, readonly=True, index=True)
    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', required=True, ondelete='cascade', index=True)
    pallet_quantity = fields.Integer(string='Pallet Quantity', required=True, default=1)
    template_lines = fields.One2many('bonded.inbound.pallet.group.line', 'pallet_group_id', string='Pallet Structure')
    inbound_lines = fields.One2many('bonded.inbound.line', 'pallet_group_id', string='Generated Inbound Lines', readonly=True)

    _sql_constraints = [
        ('pallet_quantity_positive', 'check(pallet_quantity > 0)', 'Pallet quantity must be greater than zero.'),
    ]

    def init(self):
        super().init()
        self.env.cr.execute('ALTER TABLE bonded_inbound_pallet_group DROP COLUMN IF EXISTS pallet_number_prefix, DROP COLUMN IF EXISTS pallet_start_number, DROP COLUMN IF EXISTS pallet_number_digits')
        self.env.cr.execute('ALTER TABLE bonded_inbound_pallet_group DROP CONSTRAINT IF EXISTS bonded_inbound_pallet_group_bonded_inbound_id_fkey, ADD CONSTRAINT bonded_inbound_pallet_group_bonded_inbound_id_fkey FOREIGN KEY (bonded_inbound_id) REFERENCES bonded_inbound (id) ON DELETE CASCADE')
        self.env.cr.execute('ALTER TABLE bonded_inbound_line DROP CONSTRAINT IF EXISTS bonded_inbound_line_pallet_group_id_fkey, ADD CONSTRAINT bonded_inbound_line_pallet_group_id_fkey FOREIGN KEY (pallet_group_id) REFERENCES bonded_inbound_pallet_group (id) ON DELETE CASCADE')

    @api.depends('inbound_lines.pallet_no')
    def _compute_name(self):
        for rec in self:
            pallet_nos = sorted(set(rec.inbound_lines.mapped('pallet_no')))
            if not pallet_nos:
                rec.name = False
                continue
            rec.name = '%s ~ %s (%s)' % (pallet_nos[0], pallet_nos[-1], len(pallet_nos))


class BondedInboundPalletGroupLine(models.Model):
    _name = 'bonded.inbound.pallet.group.line'
    _description = 'Bonded Inbound Identical Pallet Group Line'
    _order = 'id desc'

    pallet_group_id = fields.Many2one('bonded.inbound.pallet.group', string='Pallet Group', required=True, ondelete='cascade', index=True)
    bonded_product_id = fields.Many2one('bonded.product', string='Bonded Product Filing', required=True, ondelete='restrict', index=True)
    product_id = fields.Many2one(related='bonded_product_id.product_id', string='Product', store=True, readonly=True, index=True)
    uom_id = fields.Many2one(related='bonded_product_id.uom_id', string='UoM', store=True, readonly=True)
    planned_qty = fields.Float(string='Quantity per Pallet', required=True, default=1.0)
