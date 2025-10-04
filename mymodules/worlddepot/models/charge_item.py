from odoo import models, fields, api


class ChargeUnit(models.Model):
    _name = 'world.depot.charge.unit'
    _description = 'Charge Unit'
    _rec_name = 'name'

    name = fields.Char(string='Unit Name', required=True)
    description = fields.Text(string='Description')


class ChargeItem(models.Model):
    _name = 'world.depot.charge.item'
    _description = 'Charge Item'
    _rec_name = 'full_item_name'

    item_name = fields.Char(string='Item Name', required=True)
    parent_id = fields.Many2one('world.depot.charge.item', string='Parent Item')
    full_item_name = fields.Char(string='Full Item Name', compute='_compute_full_item_name', store=True)
    unit_id = fields.Many2one('world.depot.charge.unit', string='Unit')
    description = fields.Text(string='Description')

    @api.depends('item_name', 'parent_id.full_item_name')
    def _compute_full_item_name(self):
        for record in self:
            if record.parent_id:
                record.full_item_name = f"{record.parent_id.full_item_name} / {record.item_name}"
            else:
                record.full_item_name = record.item_name
