from odoo import models, fields, api
from odoo.exceptions import UserError

class ChargeModuleSelector(models.TransientModel):
    _name = 'worlddepot.charge.module.selector'
    _description = 'Wizard: Select Charge Module'

    module_id = fields.Many2one(
        'world.depot.charge.module',
        string='Charge Module',
        required=True,
        domain=[('state', '=', 'active')],
        help='Select a charge module to apply.'
    )
    type = fields.Selection(
        related='module_id.type',
        string="Type", 
        readonly=True
    )
    description = fields.Text(
        related='module_id.description', 
        string="Description", 
        readonly=True
    )

    # Change to related field instead of computed
    charge_item_ids = fields.One2many(
        'world.depot.charge.module.item',
        'module_id',
        string='Module Items',
        related='module_id.charge_item_ids',  # Related field
        readonly=True,
    )
    
    operation = fields.Selection(
        [('replace', 'Replace (remove existing items)'), ('append', 'Append (add items)')],
        string='Operation',
        default='replace',
        required=True,
        help='Choose whether to replace the target record items or append module items to them.'
    )
    

    def apply_to(self):
        self.ensure_one()
        model = self.env.context.get('active_model')
        res_id = self.env.context.get('active_id')
        field_name = self.env.context.get('field_name', 'charge_module_id')
        items_field = self.env.context.get('target_items_field', 'charge_item_ids')
        parent_field_name = self.env.context.get('parent_field_name')
        child_model = self.env.context.get('child_model')
        
        if not parent_field_name:
            raise UserError('No parent field name provided in context (parent_field_name).')
        
        if not child_model:
            raise UserError('No child model provided in context (child_model).')

        if not model or not res_id:
            raise UserError('No target record provided in context (active_model/active_id).')

        record = self.env[model].browse(res_id)
        if not record:
            raise UserError('Target record not found.')

        if field_name not in record._fields:
            raise UserError(f"Target model doesn't have field '{field_name}' to write the module.")

        record.write({field_name: self.module_id.id})

        # If module has items and target has an items one2many, either replace or append
        module_items = self.module_id.charge_item_ids
        if module_items and items_field in record._fields and record[items_field] is not None:
            new_lines = []
            for item in module_items:
                vals = {
                    parent_field_name: record.id,
                    'charge_item_id': item.charge_item_id.id,
                    'quantity': item.quantity,
                    'charge_unit_id': item.charge_unit_id.id if item.charge_unit_id else False,
                    'unit_price': item.unit_price,
                    'description': item.description,
                    'currency_id': item.currency_id.id if item.currency_id else False,
                }
                new_lines.append((0, 0, vals))

            if self.operation == 'replace':
                # Remove existing items first
                existing_items = self.env[child_model].search([(parent_field_name, '=', record.id)])
                if existing_items:
                    existing_items.unlink()
                    
                # Only write new lines if there are any
                if new_lines:
                    record.write({items_field: new_lines})
            else:
                record.write({items_field: new_lines})

        return {'type': 'ir.actions.act_window_close'}