from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class QoolingInboundForm(models.Model):
    _name = "wd.qooling.inbound.form"
    _inherit = "wd.qooling.media.evidence.mixin"
    _description = "Qooling Inbound Form"
    _order = "date desc, id desc"

    name = fields.Char(
        string="Number",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
        ],
        string="Status",
        default="draft",
        required=True,
        copy=False,
    )
    location_id = fields.Many2one("stock.warehouse", string="Location", required=True)
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    supervisor_id = fields.Many2one("res.users", string="Supervisor", required=True)
    ref_no = fields.Char(string="Business Reference")
    goods_status = fields.Selection(
        [
            ("free_union_goods", "Free union goods"),
            ("t1", "T1"),
        ],
        string="Goods Status",
        required=True,
    )
    unloading_permission = fields.Selection(
        [
            ("yes", "Yes"),
            ("no_stop_unloading", "No, stop unloading and ask project manager"),
        ],
        string="Unloading permission received?",
        required=True,
    )
    mrn_number = fields.Char(string="MRN Number")
    seal_number = fields.Char(string="Seal Number")
    skal_bio_product = fields.Selection(
        [("yes", "Yes"), ("no", "No")],
        string="SKAL / BIO Product",
    )
    bl_number = fields.Char(string="B/L")
    container_shipment_number = fields.Char(string="Container Number / Shipment Number")
    filled_in_by_id = fields.Many2one(
        "res.users",
        string="Filled in by",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    filing_date = fields.Date(
        string="Filing date",
        required=True,
        default=fields.Date.context_today,
    )
    checked_visible_damage = fields.Boolean(string="Checked for visible damage or packaging issues")
    checked_received_quantity = fields.Boolean(string="Number received has been checked")
    checked_product_quality = fields.Boolean(string="Product quality and condition have been checked")
    packaging_condition = fields.Selection(
        [("good", "Good"), ("not_good", "Not good")],
        string="Packaging condition",
    )
    gas_measurement = fields.Selection(
        [
            ("yes", "Yes"),
            ("no", "No"),
            ("not_applicable", "Not Applicable"),
        ],
        string="Gas measurement",
    )
    gas_measurement_status = fields.Selection(
        [
            ("safe", "Safe"),
            ("ventilation_required", "Ventilation required"),
            ("dangerous", "Dangerous"),
        ],
        string="Gas measurement Status",
    )
    ventilated = fields.Selection(
        [("yes", "Yes"), ("not_applicable", "Not applicable")],
        string="Ventilated",
    )
    status_after_ventilation = fields.Selection(
        [
            ("safe", "Safe"),
            ("ventilation_required", "Ventilation required"),
            ("dangerous", "Dangerous"),
        ],
        string="Status after ventilation",
    )
    adr = fields.Selection(
        [("yes", "Yes"), ("no", "No")],
        string="ADR",
        required=True,
    )
    un_number = fields.Selection(
        [("3171", "3171"), ("3480", "3480"), ("3481", "3481")],
        string="UN Number",
    )
    temperature_measured = fields.Selection(
        [("yes", "Yes"), ("no", "No")],
        string="Temperature measured",
    )
    pallet_temperature_registered = fields.Selection(
        [("yes", "Yes"), ("no", "No")],
        string="Temperature of each pallet is registered",
    )
    average_temperature_per_pallet = fields.Float(string="Average temperature per pallet (°C)")
    photo = fields.Binary(string="Photo", attachment=True)
    photo_ids = fields.Many2many(
        "ir.attachment",
        "wd_qooling_inbound_form_attachment_rel",
        "inbound_id",
        "attachment_id",
        string="Photos and videos",
    )
    comments = fields.Text(string="Comments")
    warehouse_signature = fields.Binary(string="Warehouse signature", attachment=True, copy=False)
    signer_id = fields.Many2one("res.users", string="Signer", readonly=True, copy=False)
    signature_time = fields.Datetime(string="Signature time", readonly=True, copy=False)
    submitted_by_id = fields.Many2one("res.users", string="Submitted by", readonly=True, copy=False)
    submitted_at = fields.Datetime(string="Submitted at", readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code("wd.qooling.inbound.form") or _("New")
            vals.setdefault("filled_in_by_id", self.env.uid)
        return super().create(vals_list)

    @api.constrains("un_number")
    def _check_un_number(self):
        allowed = {"3171", "3480", "3481"}
        for record in self:
            if record.un_number and record.un_number not in allowed:
                raise ValidationError(_("UN Number is not allowed."))

    @api.constrains("state", "warehouse_signature", "location_id", "date", "supervisor_id", "goods_status", "unloading_permission", "adr")
    def _check_submitted_requirements(self):
        for record in self:
            if record.state == "submitted" and not record.warehouse_signature:
                raise ValidationError(_("A handwritten warehouse signature is required before submission."))

    def action_sign(self, signature=None):
        self.ensure_one()
        if signature:
            self.write({
                "warehouse_signature": signature,
                "signer_id": self.env.user.id,
                "signature_time": fields.Datetime.now(),
            })

    def action_submit(self):
        for record in self:
            if not record.warehouse_signature:
                raise UserError(_("A handwritten warehouse signature is required before submission."))
            if record.adr == "yes" and (
                not record.un_number
                or not record.temperature_measured
                or not record.pallet_temperature_registered
            ):
                raise UserError(_("UN Number and temperature fields are required when ADR is Yes."))
            record.write({
                "state": "submitted",
                "signer_id": record.signer_id.id or self.env.user.id,
                "signature_time": record.signature_time or fields.Datetime.now(),
                "submitted_by_id": self.env.user.id,
                "submitted_at": fields.Datetime.now(),
            })
        return True

    def action_reset_to_draft(self):
        self.write({"state": "draft"})
        return True
