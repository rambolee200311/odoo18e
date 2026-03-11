from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ImportPickupRequirement(models.Model):
    _name = "import.pickup.requirement"
    _description = "Pickup Requirement Form"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Requirement No", copy=False, readonly=True, index=True)

    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, ondelete="restrict", index=True)
    container_lines = fields.One2many("pickup.container.line", "pickup_id", string="Container No List", copy=False)

    terminal_a = fields.Many2one('res.partner', string='Terminal of Arrival', tracking=True,related="waybill_id.terminal_a", store=True)

    pickup_end_type = fields.Selection([
        ("warehouse", "Warehouse"),
        ("other", "Other Address")
    ], string="Pickup End Point Type", default="warehouse", required=True, index=True)

    warehouse_id = fields.Many2one("stock.warehouse", string="Belonging Warehouse")
    other_address = fields.Text(string="Other Address")

    pickup_deadline = fields.Datetime(string="Pickup Deadline", required=True, index=True)
    customer_id = fields.Many2one("res.partner", string="Customer", required=True)
    customer_name = fields.Char(string="Customer Name",related="customer_id.name", store=True)

    pickup_requirements = fields.Text(string="Pickup Requirements")
    contact_info = fields.Char(string="Contact Person / Phone")

    state = fields.Selection([
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("planned", "Planned"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled")
    ], string="Requirement Status", default="draft", required=True, tracking=True, index=True)

    cancel_reason = fields.Text(string="Cancel Reason", copy=False)

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise ValidationError(_("Only draft can be submitted"))
            rec.write({
                "state": "submitted"
            })

    def action_set_planned(self):
        for rec in self:
            if rec.state != "submitted":
                raise ValidationError(_("Only submitted can be set to planned"))
            rec.write({
                "state": "planned"
            })

    def action_set_completed(self):
        for rec in self:
            if rec.state != "planned":
                raise ValidationError(_("Only submitted can be set to planned"))
            rec.write({
                "state": "completed"
            })

    def action_cancel(self):
        for rec in self:
            if rec.state not in ["draft", "submitted"]:
                raise ValidationError(_("Only draft or submitted can be cancelled"))

            if not rec.cancel_reason:
                raise ValidationError(_("Cancel reason is required"))

            rec.write({
                "state": "cancelled"
            })

    @api.model
    def create(self, vals):
        if not vals.get("name"):
            vals["name"] = self.env["ir.sequence"].sudo().next_by_code("import.pickup.requirement")
        return super().create(vals)

    @api.constrains("pickup_deadline")
    def check_deadline(self):
        for rec in self:
            if rec.pickup_deadline and rec.pickup_deadline < fields.Datetime.today():
                raise ValidationError(_("Pickup deadline must be greater than today"))

    @api.constrains("pickup_end_type", "warehouse_id", "other_address")
    def check_pickup_end(self):
        for rec in self:
            if rec.pickup_end_type == "warehouse" and not rec.warehouse_id:
                raise ValidationError(_("Warehouse must be filled when end type is warehouse"))

            if rec.pickup_end_type == "other" and not rec.other_address:
                raise ValidationError(_("Other address must be filled when end type is other"))