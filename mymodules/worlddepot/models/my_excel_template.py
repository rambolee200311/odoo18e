from odoo import _, models, fields, api
from odoo.exceptions import ValidationError


class ExcelTemplate(models.Model):
    _name = 'world.depot.excel.template'
    _description = 'Excel Template for World Depot'

    type = fields.Selection(
        selection=[('inbound', 'Inbound'), ('outbound', 'Outbound')],
        string='Type',
        required=True,
        help='Specify whether the template is for inbound or outbound operations.'
    )
    project = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        help='The project associated with this Excel template.'
    )
    remark = fields.Text(
        string='Remark',
        help='Additional notes or remarks about the template.'
    )
    template_file = fields.Binary(
        string='Template File',
        required=True,
        help='Upload the Excel template file.'
    )
    template_file_name = fields.Char(
        string='Template File Name',
        help='The name of the uploaded template file.'
    )

    @api.constrains('type', 'project')
    def _check_type_and_project(self):
        """Ensure the combination of type and project is unique."""
        for record in self:
            if self.search_count([
                ('type', '=', record.type),
                ('project', '=', record.project),
                ('id', '!=', record.id)
            ]):
                raise ValidationError(
                    _('The combination of Type and Project must be unique. Please choose a different combination.')
                )