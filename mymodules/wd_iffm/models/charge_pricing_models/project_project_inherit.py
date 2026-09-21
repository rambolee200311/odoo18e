from odoo import fields, models, _
from odoo.exceptions import AccessError

class ProjectProjectInherit(models.Model):
    _inherit = "project.project"


    quotation_id = fields.Many2one("charge.quotation", string="Quotation", index=True, tracking=True)
    vendor_cost_quotation_id = fields.Many2one("vendor.cost.quotation", string="Vendor Cost Quotation", ondelete="restrict", index=True, tracking=True)
    allowed_user_ids = fields.Many2many("res.users", "project_allowed_user_rel", "project_id", "user_id", string="Allowed Users", groups="wd_iffm.group_import_manager,base.group_system")
    payment_company_id = fields.Many2one("res.partner", string="Payment Company", index=True, tracking=True)

    def write(self, vals):
        import_freight_fields = {"quotation_id", "vendor_cost_quotation_id", "payment_company_id"}
        manager_fields = import_freight_fields | {"allowed_user_ids"}
        is_system = self.env.user.has_group("base.group_system")
        is_project_manager = self.env.user.has_group("project.group_project_manager")
        is_manager = self.env.user.has_group("wd_iffm.group_import_manager")
        is_import_user = self.env.user.has_group("wd_iffm.group_import_user")
        if not is_system and not is_project_manager and is_manager and set(vals).difference(manager_fields):
            raise AccessError(_("Import Managers can only update import freight settings and allowed users."))
        if not is_system and not is_project_manager and not is_manager and is_import_user:
            if set(vals).difference(import_freight_fields):
                raise AccessError(_("Import Users can only update import freight settings."))
            for rec in self:
                if self.env.user.id not in rec.sudo().allowed_user_ids.ids:
                    raise AccessError(_("Only allowed project users can update import freight settings."))
        return super().write(vals)
