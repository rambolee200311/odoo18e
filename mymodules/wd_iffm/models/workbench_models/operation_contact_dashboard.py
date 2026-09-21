from odoo import api, fields, models


CONTACT_ROLE_DOMAIN_MAP = {
    "shipping_agent": [("is_shipping_agent", "=", True)],
    "exporter": [("is_exporter", "=", True)],
    "importer": [("is_importer", "=", True)],
    "customs_broker": [("is_customs_broker", "=", True)],
    "notify_party": [("is_notify_party", "=", True)],
    "payment_company": [("is_payment", "=", True)],
    "receipt_company": [("is_receipt", "=", True)],
    "unassigned": [("is_shipping_line", "=", False), ("is_shipping_agent", "=", False), ("is_exporter", "=", False), ("is_importer", "=", False), ("is_customs_broker", "=", False), ("is_notify_party", "=", False), ("is_payment", "=", False), ("is_receipt", "=", False)],
    "all": [],
}


class OperationContactDashboard(models.TransientModel):
    _name = "operation.contact.dashboard"
    _description = "Operation Contact Dashboard"

    shipping_agent_count = fields.Integer(string="Shipping Line Agent Count", readonly=True)
    exporter_count = fields.Integer(string="Exporter Count", readonly=True)
    importer_count = fields.Integer(string="Importer Count", readonly=True)
    customs_broker_count = fields.Integer(string="Customs Broker Count", readonly=True)
    notify_party_count = fields.Integer(string="Notify Party Count", readonly=True)
    payment_company_count = fields.Integer(string="Payment Company Count", readonly=True)
    receipt_company_count = fields.Integer(string="Receipt Company Count", readonly=True)
    unassigned_count = fields.Integer(string="Unassigned Count", readonly=True)
    all_count = fields.Integer(string="All Contacts Count", readonly=True)

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        env_partner = self.env["res.partner"]
        for role_code, domain in CONTACT_ROLE_DOMAIN_MAP.items():
            count_field = "%s_count" % role_code
            if count_field in field_list:
                values[count_field] = env_partner.sudo().search_count(domain)
        return values

    def action_open_contacts_by_role(self):
        for rec in self:
            role_code = rec.env.context.get("contact_role_code")
            return {
                "type": "ir.actions.act_window",
                "name": rec.env.context.get("contact_role_name", "Contacts"),
                "res_model": "res.partner",
                "view_mode": "list,form",
                "views": [(rec.env.ref("wd_iffm.view_wd_iffm_partner_list").id, "list"), (False, "form")],
                "search_view_id": rec.env.ref("wd_iffm.view_wd_iffm_partner_search").id,
                "domain": CONTACT_ROLE_DOMAIN_MAP.get(role_code, []),
                "target": "current",
            }
