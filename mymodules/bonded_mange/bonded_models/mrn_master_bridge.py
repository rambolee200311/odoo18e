import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

CUSTOMS_STATUS_SELECTION = [
    ("vrij", "Vrij"),
    ("rto", "Return to Origin"),
    ("entrepot", "Bonded Warehouse"),
    ("accijns", "Excise Goods"),
    ("ivv", "Import/Export/Transit & Equivalent"),
    ("bonded", "Bonded"),
    ("non_bonded", "Free / Non-bonded"),
]

MRN_STATUS_SELECTION = [
    ("pending_declaration", "Pending Declaration"),
    ("declared", "Declared"),
    ("cleared", "Cleared"),
    ("status_changed", "Status Changed"),
    ("exception", "Exception"),
]

T1_STATUS_SELECTION = [("open", "Open"), ("closed", "Closed")]


class BondedMrnMaster(models.Model):
    _name = "bonded.mrn.master"
    _description = "MRN Master"
    _order = "id desc"
    _rec_name = "code"

    _sql_constraints = [("code_unique", "unique(code)", "MRN Code must be unique.")]

    code = fields.Char(string="MRN Code", required=True, index=True, copy=False, tracking=True)
    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", required=True, default="vrij", index=True, tracking=True)
    mrn_status = fields.Selection(MRN_STATUS_SELECTION, string="MRN Status", required=True, default="pending_declaration", index=True, tracking=True)
    t1_document_number = fields.Char(string="T1 Document Number", index=True, copy=False, tracking=True)
    t1_status = fields.Selection(T1_STATUS_SELECTION, string="T1 Status", default="open", index=True, tracking=True)
    t1_closed_date = fields.Date(string="T1 Closed Date", index=True, tracking=True)
    remark = fields.Char(string="Remark")
    active = fields.Boolean(string="Active", default=True, index=True)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company, index=True)

    def actionNormalizeMrnCode(self, code):
        return (code or "").strip().upper()

    def getMrnRegexPattern(self):
        return r"^[A-Z]{2}[A-Z0-9]{16}$"


    @api.onchange("code")
    def onchangeCodeUpper(self):
        for rec in self:
            rec.code = rec.actionNormalizeMrnCode(rec.code) or False



    @api.constrains("code")
    def checkMrnCodeFormat(self):
        regex = re.compile(self.getMrnRegexPattern())
        for rec in self:
            code = rec.actionNormalizeMrnCode(rec.code)
            if code and not regex.fullmatch(code):
                raise ValidationError(_("MRN format invalid. It must be 18 chars: 2-letter country code + 16 uppercase alphanumeric chars."))
