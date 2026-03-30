from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.http import request


class BondedCustomsMrnAuditLog(models.Model):
    _name = "bonded.customs.mrn.audit.log"
    _description = "Customs MRN Audit Log"
    _order = "id desc"

    model_name = fields.Char(string="Model", required=True, index=True, copy=False)
    res_id = fields.Integer(string="Record ID", required=True, index=True, copy=False)
    field_name = fields.Selection([("customs_status", "Customs Status"),
                                   ("origin_country", "Country of Origin"),
                                   ("goods_value", "Goods Value"),
                                   ("hs_code", "HS Code"),
                                   ("customs_code", "Customs Code"),
                                   ("mrn_id", "MRN"),
                                   ("mrn_status", "MRN Status"),
                                   ("t1_document_number", "T1 Document Number"),
                                   ("t1_status", "T1 Status"),
                                   ("t1_closed_date", "T1 Closed Date")], string="Field", required=True, index=True, copy=False)

    old_value = fields.Char(string="Old Value", copy=False)
    new_value = fields.Char(string="New Value", copy=False)
    customs_status_old = fields.Selection([
        ("vrij", "Vrij"),
        ("rto", "Return to Origin"),
        ("entrepot", "Bonded Warehouse"),
        ("accijns", "Excise Goods"),
        ("ivv", "Import/Export/Transit & Equivalent"),
        ("bonded", "Bonded"),
        ("non_bonded", "Free / Non-bonded"),
    ], string="Old Customs Status", copy=False)
    customs_status_new = fields.Selection([
        ("vrij", "Vrij"),
        ("rto", "Return to Origin"),
        ("entrepot", "Bonded Warehouse"),
        ("accijns", "Excise Goods"),
        ("ivv", "Import/Export/Transit & Equivalent"),
        ("bonded", "Bonded"),
        ("non_bonded", "Free / Non-bonded"),
    ], string="New Customs Status", copy=False)
    mrn_status_old = fields.Selection([
    ("pending_declaration", "Pending Declaration"),
    ("declared", "Declared"),
    ("cleared", "Cleared"),
    ("status_changed", "Status Changed"),
    ("exception", "Exception"),
    ], string="Old MRN Status", copy=False)
    mrn_status_new = fields.Selection([
    ("pending_declaration", "Pending Declaration"),
    ("declared", "Declared"),
    ("cleared", "Cleared"),
    ("status_changed", "Status Changed"),
    ("exception", "Exception"),
    ], string="New MRN Status", copy=False)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", store=True, readonly=True, index=True)
    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", index=True, options="{'no_create': True, 'no_open': True}")
    picking_id = fields.Many2one("stock.picking", string="Picking", index=True, options="{'no_create': True, 'no_open': True}")
    move_id = fields.Many2one("stock.move", string="Move", index=True, options="{'no_create': True, 'no_open': True}")
    quant_id = fields.Many2one("stock.quant", string="Quant", index=True, options="{'no_create': True, 'no_open': True}")
    product_id = fields.Many2one("product.product", string="Product", index=True, options="{'no_create': True, 'no_open': True}")
    action_type = fields.Selection([("automatic", "Automatic"), ("manual", "Manual"), ("import", "Import"), ("api", "API")], string="Action Type", required=True, default="manual", index=True, copy=False)
    change_reason = fields.Text(string="Change Reason", copy=False)
    operation_remark = fields.Char(string="Operation Remark", copy=False)
    user_id = fields.Many2one("res.users", string="User", required=True, default=lambda self: self.env.user, index=True, copy=False)
    operation_time = fields.Datetime(string="Operation Time", required=True, default=fields.Datetime.now, index=True, copy=False)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company, index=True, copy=False)
    operation_ip = fields.Char(string="Operation IP", copy=False, index=True)
    t1_status_old = fields.Selection([("open", "Open"), ("closed", "Closed")], string="Old T1 Status", copy=False)
    t1_status_new = fields.Selection([("open", "Open"), ("closed", "Closed")], string="New T1 Status", copy=False)

    def getRequestIpText(self):
        if not request or not getattr(request, "httprequest", None):
            return "N/A"
        xff = request.httprequest.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        return request.httprequest.remote_addr or "N/A"

    @api.model_create_multi
    def create(self, vals_list):
        ip_text = self.getRequestIpText()
        for vals in vals_list:
            vals.setdefault("operation_ip", ip_text)
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("Audit logs are immutable and cannot be edited."))

    def unlink(self):
        raise UserError(_("Audit logs cannot be deleted."))