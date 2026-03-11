from odoo import api, fields, models, _

class ProjectProjectInherit(models.Model):
    _inherit = "project.project"


    quotation_id = fields.Many2one("charge.quotation", string="Quotation", index=True, tracking=True)