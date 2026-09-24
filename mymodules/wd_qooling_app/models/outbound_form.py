from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class QoolingOutboundForm(models.Model):
    _name = "wd.qooling.outbound.form"
    _inherit = "wd.qooling.media.evidence.mixin"
    _description = "Qooling Outbound Form"
    _order = "date_arrival desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"))
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("exception_pending", "Exception Pending"),
            ("closed", "Closed"),
        ],
        default="draft",
        required=True,
        copy=False,
    )
    location_id = fields.Many2one("stock.warehouse", required=True, string="Location")
    date_arrival = fields.Datetime(
        required=True, default=fields.Datetime.now, string="Date and time arrival"
    )
    supervisor_id = fields.Many2one("res.users", required=True, string="Supervisor / Manager")
    ref_no = fields.Char(string="Reference")
    start_loading_at = fields.Datetime(required=True, default=fields.Datetime.now, string="Start time loading")
    end_loading_at = fields.Datetime(required=True, default=fields.Datetime.now, string="End time of loading")
    goods_type = fields.Selection(
        [("bonded", "Bonded"), ("non_bonded", "Non-Bonded")], required=True, string="Goods type"
    )
    mrn_number = fields.Char(string="MRN Number")
    seal_number = fields.Char(string="Seal Number")
    mrn_checked_before_release = fields.Boolean(string="MRN checked before release")
    adr = fields.Selection([("yes", "Yes"), ("no", "No")], required=True, string="ADR")
    un_number = fields.Selection(
        [("3171", "3171"), ("3480", "3480"), ("3481", "3481")], string="UN Number"
    )
    proper_shipping_name = fields.Char(string="Proper Shipping Name")
    measured_temperature = fields.Float(string="Measured temperature (°C)")
    loading_plan_discussed = fields.Boolean(string="Loading plan discussed with driver")
    adr_separation_compatibility = fields.Boolean(string="ADR separation / compatibility")
    weight_distribution = fields.Boolean(string="Weight distribution checked")
    driver_comments = fields.Text(string="Driver comments")
    driver_signature = fields.Binary(attachment=True, copy=False, string="Driver signature")
    driver_signer_id = fields.Many2one("res.users", readonly=True, copy=False, string="Driver signer")
    driver_signature_time = fields.Datetime(readonly=True, copy=False, string="Driver signature time")
    cargo_photo = fields.Binary(attachment=True, string="Photo of cargo")
    photo_ids = fields.Many2many(
        "ir.attachment", "wd_qooling_outbound_form_attachment_rel",
        "outbound_id", "attachment_id",         string="Photos and videos",
    )
    warehouse_operator_comments = fields.Text(string="Warehouse operator comments")
    warehouse_signature = fields.Binary(attachment=True, copy=False, string="Warehouse operator signature")
    warehouse_signer_id = fields.Many2one(
        "res.users", readonly=True, copy=False, string="Warehouse operator signer"
    )
    warehouse_signature_time = fields.Datetime(
        readonly=True, copy=False, string="Warehouse signature time"
    )
    filled_in_by_id = fields.Many2one(
        "res.users", required=True, readonly=True, default=lambda self: self.env.user, string="Filled in by"
    )
    filing_date = fields.Date(required=True, default=fields.Date.context_today, string="Filing date")
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    submitted_at = fields.Datetime(readonly=True, copy=False)

    # Every check is retained independently so a reviewer can see the original result.
    check_loading_visible_damage = fields.Boolean(string="Loading: visible damage or packaging issues")
    check_loading_quantity = fields.Boolean(string="Loading: quantity checked")
    cargo_packaging = fields.Boolean(string="Cargo: packaging checked")
    cargo_identification = fields.Boolean(string="Cargo: correct identification")
    cargo_secured = fields.Boolean(string="Cargo: secured on truck")
    vehicle_adr_certificate = fields.Boolean(string="Vehicle: ADR certificate")
    vehicle_fire_extinguisher = fields.Boolean(string="Vehicle: fire extinguisher")
    vehicle_adr_sign = fields.Boolean(string="Vehicle: ADR sign")
    vehicle_fixing_material = fields.Boolean(string="Vehicle: fixing material")
    vehicle_trem_card = fields.Boolean(string="Vehicle: TREM card / written instructions")
    driver_adr_certificate = fields.Boolean(string="Driver: ADR certificate")
    driver_safety_vest = fields.Boolean(string="Driver: reflective safety vest")
    driver_eye_protection = fields.Boolean(string="Driver: eye protection")
    driver_protective_gloves = fields.Boolean(string="Driver: protective gloves")
    driver_wheel_chock = fields.Boolean(string="Driver: wheel chock")
    driver_tarpaulin = fields.Boolean(string="Driver: tarpaulin")
    driver_flashlight = fields.Boolean(string="Driver: flashlight")
    driver_shovel = fields.Boolean(string="Driver: shovel")
    driver_drip_tray = fields.Boolean(string="Driver: drip tray")
    driver_eyewash = fields.Boolean(string="Driver: eyewash bottle")
    driver_warning_triangles = fields.Boolean(string="Driver: two independent warning triangles")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code("wd.qooling.outbound.form") or _("New")
            vals.setdefault("filled_in_by_id", self.env.uid)
        return super().create(vals_list)

    @api.constrains("date_arrival", "start_loading_at", "end_loading_at")
    def _check_loading_time_order(self):
        for record in self:
            if record.date_arrival > record.start_loading_at or record.start_loading_at > record.end_loading_at:
                raise ValidationError(_("Arrival, start loading, and end loading times must be in chronological order."))

    @api.constrains("un_number")
    def _check_un_number(self):
        for record in self:
            if record.un_number and record.un_number not in {"3171", "3480", "3481"}:
                raise ValidationError(_("UN Number is not allowed."))

    @api.constrains(
        "state", "driver_signature", "driver_signer_id", "driver_signature_time",
        "warehouse_signature", "warehouse_signer_id", "warehouse_signature_time",
    )
    def _check_submitted_signatures(self):
        for record in self:
            if record.state != "submitted":
                continue
            for signature, signer, signature_time, label in (
                (record.driver_signature, record.driver_signer_id, record.driver_signature_time, _("Driver")),
                (record.warehouse_signature, record.warehouse_signer_id, record.warehouse_signature_time,
                 _("Warehouse operator")),
            ):
                if signature and (not signer or not signature_time):
                    raise ValidationError(_("%s signature audit fields are required.") % label)

    def action_sign_driver(self, signature=None):
        self.ensure_one()
        if signature:
            self.write({
                "driver_signature": signature,
                "driver_signer_id": self.env.uid,
                "driver_signature_time": fields.Datetime.now(),
            })
        return True

    def action_sign_warehouse(self, signature=None):
        self.ensure_one()
        if signature:
            self.write({
                "warehouse_signature": signature,
                "warehouse_signer_id": self.env.uid,
                "warehouse_signature_time": fields.Datetime.now(),
            })
        return True

    def action_submit(self):
        for record in self:
            if record.date_arrival > record.start_loading_at or record.start_loading_at > record.end_loading_at:
                raise UserError(_("Arrival, start loading, and end loading times must be in chronological order."))
            record.write({
                "state": "submitted",
                "submitted_by_id": self.env.uid,
                "submitted_at": fields.Datetime.now(),
            })
        return True

    def action_reset_to_draft(self):
        self._check_reviewer()
        self.write({"state": "draft"})
        return True

    def action_mark_exception(self):
        self._check_reviewer()
        self.write({"state": "exception_pending"})
        return True

    def action_close(self):
        self._check_reviewer()
        self.write({"state": "closed"})
        return True

    def _check_reviewer(self):
        if not self.env.user.has_group("wd_qooling_app.group_qooling_outbound_reviewer") and not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only an Outbound reviewer can perform this action."))
