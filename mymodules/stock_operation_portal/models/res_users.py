# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = 'res.users'

    stock_operation_owner_line_ids = fields.Many2many('res.partner', 'stock_operation_portal_user_owner_rel', 'user_id', 'owner_id', string='Visible Stock Operation Owners', copy=False)
    stock_operation_project_line_ids = fields.Many2many('project.project', 'stock_operation_portal_user_project_rel', 'user_id', 'project_id', string='Visible Stock Operation Projects', copy=False)

    @api.onchange('stock_operation_owner_line_ids')
    def onchange_stock_operation_owner_line_ids(self):
        for rec in self:
            valid_projects = rec.stock_operation_project_line_ids.filtered(lambda project: project.owner in rec.stock_operation_owner_line_ids)
            added_owner_ids = [owner_id for owner_id in rec.stock_operation_owner_line_ids.ids if owner_id not in rec._origin.stock_operation_owner_line_ids.ids]
            default_projects = rec.env['project.project'].sudo().search([('owner', 'in', added_owner_ids)])
            rec.stock_operation_project_line_ids = valid_projects | default_projects

    @api.constrains('stock_operation_owner_line_ids', 'stock_operation_project_line_ids')
    def check_stock_operation_project_owner(self):
        for rec in self:
            invalid_projects = rec.stock_operation_project_line_ids.filtered(lambda project: project.owner not in rec.stock_operation_owner_line_ids)
            if invalid_projects:
                raise ValidationError(_('Visible Stock Operation Projects must belong to Visible Stock Operation Owners.'))
