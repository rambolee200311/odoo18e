from odoo import _, api, fields, models
from odoo.exceptions import UserError


CHECK_SELECTION = [("yes", "Ja"), ("no", "Nee")]


class QoolingTemperatureRecord(models.Model):
    _name = "wd.qooling.temperature.record"
    _inherit = "wd.qooling.media.evidence.mixin"
    _description = "Qooling Temperature Record"
    _order = "date desc, id desc"

    name = fields.Char(
        string="Number", required=True, readonly=True, copy=False,
        default=lambda self: _("New"),
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("exception_pending", "Exception Pending"),
            ("closed", "Closed"),
        ],
        required=True, default="draft", copy=False,
    )
    date = fields.Datetime(required=True, default=fields.Datetime.now)
    manager_id = fields.Many2one("res.users", string="Manager", required=True)
    customer = fields.Char(string="Customer", required=True)
    container_number = fields.Char(string="Container Number", required=True)
    location_id = fields.Many2one("stock.warehouse", string="Location")
    filled_in_by_id = fields.Many2one(
        "res.users", string="Filled in by", required=True, readonly=True,
        default=lambda self: self.env.user,
    )
    filing_date = fields.Date(
        string="Filing date", required=True, default=fields.Date.context_today
    )
    total_pallets = fields.Integer(string="Total Pallets", compute="_compute_total_pallets", store=True)
    quick_temperature = fields.Float(string="Quick temperature (°C)", copy=False)
    line_ids = fields.One2many(
        "wd.qooling.temperature.record.line", "record_id",
        string="Pallet temperatures", copy=True,
    )
    packaging_damage = fields.Selection(CHECK_SELECTION, string="Packaging visible damage")
    unpacked_housing_damage = fields.Selection(
        CHECK_SELECTION, string="Unpackaged product housing visible damage"
    )
    electrolyte_leakage = fields.Selection(CHECK_SELECTION, string="Electrolyte leakage")
    storage_stability = fields.Selection(CHECK_SELECTION, string="Storage stability")
    photo = fields.Binary(
        string="Legacy photo",
        attachment=True,
        help="Legacy compatibility field. New evidence must use photo_ids.",
    )
    photo_ids = fields.Many2many(
        "ir.attachment",
        "wd_qooling_temperature_record_attachment_rel",
        "record_id",
        "attachment_id",
        string="Photos and videos",
    )
    comments = fields.Text(string="Comments")
    signature = fields.Binary(string="Signature", attachment=True, copy=False)
    signer_id = fields.Many2one("res.users", string="Signer", readonly=True, copy=False)
    signature_time = fields.Datetime(string="Signature time", readonly=True, copy=False)
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    submitted_at = fields.Datetime(readonly=True, copy=False)

    @api.depends("line_ids")
    def _compute_total_pallets(self):
        for record in self:
            record.total_pallets = len(record.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code(
                    "wd.qooling.temperature.record"
                ) or _("New")
            vals.setdefault("filled_in_by_id", self.env.uid)
        return super().create(vals_list)

    def action_sign(self, signature=None):
        self.ensure_one()
        if signature:
            self.write({
                "signature": signature,
                "signer_id": self.env.uid,
                "signature_time": fields.Datetime.now(),
            })
        return True

    def action_submit(self):
        for record in self:
            if not record.signature:
                raise UserError(_("A handwritten signature is required before submission."))
            record.write({
                "state": "submitted",
                "signer_id": record.signer_id.id or self.env.uid,
                "signature_time": record.signature_time or fields.Datetime.now(),
                "submitted_by_id": self.env.uid,
                "submitted_at": fields.Datetime.now(),
            })
        return True

    def action_clear_lines(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft temperature records can be cleared."))
            record.line_ids.with_context(allow_temperature_line_unlink=True).sudo().unlink()
            record.quick_temperature = False
        return True

    def action_add_quick_temperature(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft temperature records can receive new readings."))
            record.line_ids.create({
                "record_id": record.id,
                "temperature": record.quick_temperature,
            })
            record.quick_temperature = False
        return True

    def _check_supervisor(self):
        if not self.env.user.has_group("wd_qooling_app.group_temperature_supervisor") and not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only a Temperature Supervisor can perform this action."))

    def action_mark_exception(self):
        self._check_supervisor()
        self.write({"state": "exception_pending"})
        return True

    def action_close(self):
        self._check_supervisor()
        self.write({"state": "closed"})
        return True

    def action_reset_to_draft(self):
        self._check_supervisor()
        self.write({"state": "draft"})
        return True


class QoolingTemperatureRecordLine(models.Model):
    _name = "wd.qooling.temperature.record.line"
    _description = "Qooling Temperature Record Pallet"
    _order = "sequence, id"

    record_id = fields.Many2one(
        "wd.qooling.temperature.record", required=True, ondelete="cascade",
        index=True, readonly=True,
    )
    sequence = fields.Integer(default=10, copy=False, index=True)
    pallet_number = fields.Char(
        string="Pallet", required=True, readonly=True, copy=False,
    )
    temperature = fields.Float(string="Temperature (°C)")

    @api.model_create_multi
    def create(self, vals_list):
        next_numbers = {}
        for vals in vals_list:
            record = self.env["wd.qooling.temperature.record"].browse(vals.get("record_id"))
            if record:
                if record.state != "draft":
                    raise UserError(_("Pallet temperatures can only be added in draft."))
                if record.id not in next_numbers:
                    next_numbers[record.id] = self.search_count([("record_id", "=", record.id)])
                next_numbers[record.id] += 1
                vals["sequence"] = next_numbers[record.id] * 10
                vals["pallet_number"] = "pallet%d" % next_numbers[record.id]
        return super().create(vals_list)

    def write(self, vals):
        if any(line.record_id.state != "draft" for line in self):
            raise UserError(_("Pallet temperatures can only be modified in draft."))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get("allow_temperature_line_unlink"):
            raise UserError(_("Pallet lines cannot be deleted individually. Use Clear all pallets."))
        return super().unlink()
