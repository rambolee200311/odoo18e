from odoo import api, fields, models, _
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
OPERATION_TYPE = [
    ('handover', 'Handover'),
    ('clearance', 'Clearance'),

]
class ChargeItemInherit(models.Model):
    _inherit = "world.depot.charge.item"

    account_account_id = fields.Many2one("account.account", string="Account", ondelete="restrict", index=True)
    tab_category = fields.Selection(
        TAB_CATEGORY_LIST,
        string="Quotation Charge Category",
    )
    child_ids = fields.One2many(
        'world.depot.charge.item',
        'parent_id',
        string='Child Items'
    )
    operation_type = fields.Selection(
        OPERATION_TYPE,
        string='Operation Type',
        required=True,
    )
    is_leaf = fields.Boolean(string='Is Leaf', compute='_compute_is_leaf_data', store=True)

    charge_based_on_max = fields.Boolean(string='Charge Based on Max Quantity container or hscode')
    @api.depends('child_ids', 'parent_id', 'tab_category')
    def _compute_is_leaf_data(self):
        for record in self:
            record.is_leaf = not bool(record.child_ids)