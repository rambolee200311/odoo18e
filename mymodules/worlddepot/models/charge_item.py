from odoo import models, fields, api

TAB_CATEGORY_LIST = [
    ("thc", "THC Handling"),
    ("customs", "Customs Formalities"),
    ("trucking", "Trucking"),
    ("wh_in", "Warehousing - Inbound"),
    ("storage", "Warehousing - Storage"),
    ("wh_out", "Warehousing - Outbound"),
    ("wh_extra", "Warehousing - Extra handling"),
    ("wh_pack", "Warehousing - Packaging"),
    ("wh_monthly", "Warehousing - Monthly fixed"),
    ("wh_other", "Warehousing - Other"),
]
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
    full_item_name = fields.Char(string='Full Item Name', compute='_compute_full_item_name', store=True, recursive=True)
    unit_id = fields.Many2one('world.depot.charge.unit', string='Unit')
    description = fields.Text(string='Description')
    tab_category = fields.Selection(
        TAB_CATEGORY_LIST,
        string="Charge Category",
    )
    child_ids = fields.One2many(
        'world.depot.charge.item',
        'parent_id',
        string='Child Items'
    )
    operation_type = fields.Selection(
        [
            ('inbound', 'Inbound'),
            ('outbound', 'Outbound'),
            ('transfer', 'Transfer'),
        ],
        string='Operation Type',
        required=True,
    )
    is_leaf = fields.Boolean(string='Is Leaf', compute='_compute_is_leaf_data', store=True)

    @api.depends('child_ids', 'parent_id','tab_category')
    def _compute_is_leaf_data(self):
        for record in self:
            record.is_leaf = not bool(record.child_ids)

    @api.depends('item_name', 'parent_id.full_item_name')
    def _compute_full_item_name(self):
        for record in self:
            if record.parent_id:
                record.full_item_name = f"{record.parent_id.full_item_name} / {record.item_name}"
            else:
                record.full_item_name = record.item_name
