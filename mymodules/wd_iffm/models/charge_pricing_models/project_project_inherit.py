from odoo import api, fields, models, _

class ProjectProjectInherit(models.Model):
    _inherit = "project.project"


    quotation_id = fields.Many2one("charge.quotation", string="Quotation", index=True, tracking=True)
    allowed_user_ids = fields.Many2many(
        "res.users",
        "project_allowed_user_rel",
        "project_id",
        "user_id",
        string="Allowed Users",
    )
    payment_company_id = fields.Many2one("res.partner", string="Payment Company", index=True, tracking=True)
