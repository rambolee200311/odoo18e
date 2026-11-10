# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class BondedInboundPalletGroupWizard(models.TransientModel):
    _name = 'bonded.inbound.pallet.group.wizard'
    _description = 'Wizard: Generate Identical Bonded Inbound Pallets'

    bonded_inbound_id = fields.Many2one('bonded.inbound', string='Bonded Inbound', required=True, readonly=True, ondelete='cascade', index=True)
    pallet_group_id = fields.Many2one('bonded.inbound.pallet.group', string='Pallet Group', ondelete='restrict', index=True)
    pallet_quantity = fields.Integer(string='Pallet Quantity', required=True, default=1)
    bonded_book_id = fields.Many2one(related='bonded_inbound_id.bonded_book_id', string='Bonded Book', readonly=True)
    project_category_id = fields.Many2one(related='bonded_inbound_id.project_id.category', string='Project Category', readonly=True)
    template_lines = fields.One2many('bonded.inbound.pallet.group.wizard.line', 'pallet_group_wizard_id', string='Pallet Structure')

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        inbound_id = result.get('bonded_inbound_id') or self.env.context.get('default_bonded_inbound_id')
        inbound = self.env['bonded.inbound'].sudo().browse(inbound_id).exists()
        if inbound:
            result.setdefault('bonded_inbound_id', inbound.id)
        return result

    @api.onchange('pallet_group_id')
    def onchange_pallet_group_id(self):
        for rec in self:
            group = rec.pallet_group_id
            if not group:
                continue
            if group.bonded_inbound_id != rec.bonded_inbound_id:
                raise ValidationError(_('The selected pallet group must belong to the bonded inbound instruction.'))
            rec.pallet_quantity = group.pallet_quantity
            rec.template_lines = [(5, 0, 0)] + [(0, 0, {'bonded_product_id': line.bonded_product_id.id, 'planned_qty': line.planned_qty}) for line in group.template_lines]

    def check_inbound_editable(self):
        for rec in self:
            inbound = rec.bonded_inbound_id
            if inbound.state != 'draft':
                raise UserError(_('Identical pallet groups can only be maintained while the bonded inbound instruction is in draft.'))
            if inbound.t1_customs_file_ids or inbound.picking_id or inbound.line_ids.mapped('package_id'):
                raise UserError(_('Identical pallet groups cannot be maintained after a customs declaration, package, or stock picking exists.'))
            if rec.pallet_group_id and rec.pallet_group_id.bonded_inbound_id != inbound:
                raise ValidationError(_('The selected pallet group must belong to the bonded inbound instruction.'))
            if rec.pallet_quantity <= 0:
                raise ValidationError(_('Pallet quantity must be greater than zero.'))
            if not rec.template_lines:
                raise ValidationError(_('Please add at least one product to the pallet structure.'))
            bonded_product_ids = set(rec.template_lines.mapped('bonded_product_id').ids)
            if len(bonded_product_ids) != len(rec.template_lines):
                raise ValidationError(_('Each bonded product filing can only appear once in a pallet group.'))
            pallet_group_domain = [('bonded_inbound_id', '=', inbound.id)]
            if rec.pallet_group_id:
                pallet_group_domain.append(('id', '!=', rec.pallet_group_id.id))
            pallet_groups = self.env['bonded.inbound.pallet.group'].sudo().search(pallet_group_domain)
            if any(bonded_product_ids == set(group.template_lines.mapped('bonded_product_id').ids) for group in pallet_groups):
                raise ValidationError(_('A pallet group with the same bonded product structure already exists.'))

    def generate_inbound_lines(self, pallet_group):
        for rec in self:
            pallet_number_prefix = rec.bonded_inbound_id.cntr_no or rec.bonded_inbound_id.name
            existing_pallet_nos = set(self.env['bonded.inbound.line'].sudo().search([('bonded_inbound_id', '=', rec.bonded_inbound_id.id)]).mapped('pallet_no'))
            existing_pallet_numbers = [int(pallet_no.rsplit('-', 1)[1]) for pallet_no in existing_pallet_nos if pallet_no.startswith('%s-' % pallet_number_prefix) and pallet_no.rsplit('-', 1)[1].isdigit()]
            pallet_start_number = max(existing_pallet_numbers, default=0) + 1
            pallet_nos = [f'{pallet_number_prefix}-{number:03d}' for number in range(pallet_start_number, pallet_start_number + pallet_group.pallet_quantity)]
            duplicate_pallet_nos = sorted(set(pallet_nos) & existing_pallet_nos)
            if duplicate_pallet_nos:
                raise ValidationError(_('Pallet numbers already exist on this inbound instruction: %s') % ', '.join(duplicate_pallet_nos))
            inbound_line_vals = []
            for pallet_no in pallet_nos:
                for template_line in pallet_group.template_lines:
                    inbound_line_vals.append({'bonded_inbound_id': rec.bonded_inbound_id.id, 'pallet_group_id': pallet_group.id, 'bonded_product_id': template_line.bonded_product_id.id, 'product_id': template_line.product_id.id, 'pallet_no': pallet_no, 'planned_qty': template_line.planned_qty})
            self.env['bonded.inbound.line'].create(inbound_line_vals)

    def action_generate(self):
        for rec in self:
            rec.check_inbound_editable()
            if rec.pallet_group_id:
                raise UserError(_('Please use Update and Regenerate for an existing pallet group.'))
            pallet_group = self.env['bonded.inbound.pallet.group'].create({'bonded_inbound_id': rec.bonded_inbound_id.id, 'pallet_quantity': rec.pallet_quantity})
            self.env['bonded.inbound.pallet.group.line'].create([{'pallet_group_id': pallet_group.id, 'bonded_product_id': line.bonded_product_id.id, 'planned_qty': line.planned_qty} for line in rec.template_lines])
            rec.generate_inbound_lines(pallet_group)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_update_and_regenerate(self):
        for rec in self:
            rec.check_inbound_editable()
            if not rec.pallet_group_id:
                raise UserError(_('Please select a pallet group to update.'))
            rec.pallet_group_id.inbound_lines.unlink()
            rec.pallet_group_id.template_lines.unlink()
            rec.pallet_group_id.write({'pallet_quantity': rec.pallet_quantity})
            self.env['bonded.inbound.pallet.group.line'].create([{'pallet_group_id': rec.pallet_group_id.id, 'bonded_product_id': line.bonded_product_id.id, 'planned_qty': line.planned_qty} for line in rec.template_lines])
            rec.generate_inbound_lines(rec.pallet_group_id)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_delete_pallet_group(self):
        for rec in self:
            rec.check_inbound_editable()
            if not rec.pallet_group_id:
                raise UserError(_('Please select a pallet group to delete.'))
            rec.pallet_group_id.inbound_lines.unlink()
            rec.pallet_group_id.unlink()
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class BondedInboundPalletGroupWizardLine(models.TransientModel):
    _name = 'bonded.inbound.pallet.group.wizard.line'
    _description = 'Wizard: Identical Bonded Inbound Pallet Product'
    _order = 'id desc'

    pallet_group_wizard_id = fields.Many2one('bonded.inbound.pallet.group.wizard', string='Pallet Group Wizard', required=True, ondelete='cascade', index=True)
    bonded_product_id = fields.Many2one('bonded.product', string='Bonded Product Filing', required=True, ondelete='restrict', index=True)
    product_id = fields.Many2one(related='bonded_product_id.product_id', string='Product', readonly=True)
    uom_id = fields.Many2one(related='bonded_product_id.uom_id', string='UoM', readonly=True)
    planned_qty = fields.Float(string='Quantity per Pallet', required=True, default=1.0)
