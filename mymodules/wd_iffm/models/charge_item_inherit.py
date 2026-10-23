from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
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
    ('transport', 'Transportation'),
    ('inbound', 'Inbound'),
    ('outbound', 'Outbound'),
]
class ChargeItemInherit(models.Model):
    _inherit = "world.depot.charge.item"
    _order = "id asc"

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
    )
    charge_billing_object = fields.Selection([('carton', 'Carton'), ('pallet', 'Pallet')], string='Billing Object', index=True)
    is_weight_tier = fields.Boolean(string='Use Gross Weight Tier')
    minimum_gross_weight = fields.Float(string='Minimum Gross Weight (kg)', default=0.0)
    maximum_gross_weight = fields.Float(string='Maximum Gross Weight (kg, inclusive; 0/blank = no upper limit)')
    is_leaf = fields.Boolean(string='Is Leaf', compute='_compute_is_leaf_data', store=True)

    charge_based_on_max = fields.Boolean(string='Charge Based on Max Quantity container or hscode')
    active = fields.Boolean(string="Active", default=True, index=True)
    @api.depends('child_ids', 'parent_id', 'tab_category')
    def _compute_is_leaf_data(self):
        for record in self:
            record.is_leaf = not bool(record.child_ids)

    @api.constrains('charge_billing_object', 'is_weight_tier', 'minimum_gross_weight', 'maximum_gross_weight')
    def check_weight_tier(self):
        for rec in self:
            if rec.is_weight_tier and not rec.charge_billing_object:
                raise ValidationError(_('Weight-tier charge items require a billing object.'))
            if rec.is_weight_tier and rec.minimum_gross_weight < 0:
                raise ValidationError(_('Minimum gross weight cannot be negative.'))
            if rec.is_weight_tier and rec.maximum_gross_weight and rec.maximum_gross_weight <= rec.minimum_gross_weight:
                raise ValidationError(_('Maximum gross weight must be greater than minimum gross weight.'))
