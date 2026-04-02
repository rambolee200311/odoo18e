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

    pickup_scene = fields.Selection(
        [
            ("to_our_warehouse", "Pick up to our warehouse"),
            ("to_customer_address", "Pick up to customer's designated location"),
            ("customer_self_pickup", "Customer arranges self-pickup"),
        ],
        string="Pickup Scene",
        default='to_our_warehouse',
        required=True,
        index=True,
        tracking=True,
    )


    pickup_request_datetime = fields.Datetime(
        string="Pickup Request Date", required=True, default=fields.Datetime.now, tracking=True
    )


    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Our Warehouse",
        tracking=True,
        help="Only required in 'Pick up to our warehouse' scenario",
    )


    delivery_country_id = fields.Many2one("res.country", string="Delivery Country",
                                          default=lambda self: self._default_country_nl())

    @api.model
    def _default_country_nl(self):
        return self.env["res.country"].search([("code", "=", "NL")], limit=1)

    delivery_city = fields.Char(string="Delivery City")
    delivery_zip = fields.Char(string="Delivery Postal Code")
    delivery_street = fields.Char(string="Delivery Street Address")

    delivery_contact_id = fields.Many2one("res.partner", string="Delivery Contact" ,tracking=True)
    delivery_phone = fields.Char(string="Delivery Phone" ,tracking=True)
    delivery_requirement = fields.Text(string="Delivery Requirements")

    # Scene 3: Customer Self Pickup
    self_pickup_contact_id = fields.Many2one("res.partner",string="Self-Pickup Contact" ,tracking=True)
    self_pickup_phone = fields.Char(string="Self-Pickup Phone" ,tracking=True)
    self_pickup_remark = fields.Text(string="Self-Pickup Remark")

    warehouse_contact_id = fields.Many2one("res.partner", string="Warehouse Contact" ,tracking=True)
    contact_info = fields.Char(string="Contact Info" ,tracking=True)


    pickup_requirements = fields.Text(string="Pickup Requirements")
    state = fields.Selection([
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("planned", "Planned"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled")
    ], string="Requirement Status", default="draft", required=True, tracking=True, index=True)

    cancel_reason = fields.Text(string="Cancel Reason", copy=False)


    @api.onchange("waybill_id")
    def _onchange_waybill_id(self):
        for rec in self:
            rec.container_lines = [(5, 0, 0)]
            if not rec.waybill_id:
                continue
            rec.container_lines = [
                (0, 0, {"waybill_container_id": c.id})
                for c in rec.waybill_id.container_ids
            ]

    @api.constrains("pickup_request_datetime")
    def _check_pickup_request_datetime(self):
        for rec in self:
            if not rec.pickup_request_datetime:
                raise ValidationError(_("Pickup request date is required."))

    @api.constrains("waybill_id", "container_lines")
    def _check_container_lines(self):
        for rec in self:
            if not rec.container_lines:
                raise ValidationError(_("At least one container must be selected."))
            invalid = rec.container_lines.filtered(lambda l: l.waybill_container_id.waybill_id != rec.waybill_id)
            if invalid:
                raise ValidationError(_("The container must belong to the current waybill."))

    @api.constrains(
        "pickup_scene",
        "warehouse_id",
        "delivery_country_id", "delivery_city", "delivery_zip", "delivery_street", "delivery_contact_id", "delivery_phone",
         "self_pickup_phone",
        "contact_info",
    )
    def _check_scene_required_fields(self):
        for rec in self:
            if not rec.contact_info:
                raise ValidationError(_("Contact information is required."))

            if rec.pickup_scene == "to_our_warehouse":
                if not rec.warehouse_id:
                    raise ValidationError(
                        _("For the 'Pick up to our warehouse' scenario, the warehouse must be selected."))
                if not rec.warehouse_contact_id:
                    raise ValidationError(
                        _("For the 'Pick up to our warehouse' scenario, the warehouse contact must be selected."))
                if not rec.contact_info:
                    raise ValidationError(
                        _("For the 'Pick up to our warehouse' scenario, the warehouse contact info must be provided."))

            elif rec.pickup_scene == "to_customer_address":
                missing = []
                if not rec.delivery_country_id:
                    missing.append(_("Delivery country"))
                if not rec.delivery_city:
                    missing.append(_("Delivery city"))
                if not rec.delivery_zip:
                    missing.append(_("Delivery postal code"))
                if not rec.delivery_street:
                    missing.append(_("Delivery street address"))
                if not rec.delivery_contact_id:
                    missing.append(_("Delivery contact"))
                if not rec.delivery_phone:
                    missing.append(_("Delivery phone"))
                if missing:
                    raise ValidationError(
                        _("The following required fields are missing for the 'Pick up to customer's designated location' scenario: %s") % ", ".join(
                            missing))

            elif rec.pickup_scene == "customer_self_pickup":
                missing = []
                if not rec.self_pickup_contact_id:
                    missing.append(_("Self-pickup contact"))
                if not rec.self_pickup_phone:
                    missing.append(_("Self-pickup phone"))
                if missing:
                    raise ValidationError(
                        _("The following required fields are missing for the 'Customer arranges self-pickup' scenario: %s") % ", ".join(
                            missing))


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

    @api.model_create_multi
    def create(self, vals_list):
        seq_model = self.env["ir.sequence"].sudo()
        for vals in vals_list:
            if not vals.get("name"):
                vals["name"] = seq_model.next_by_code("import.pickup.requirement")
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state not in ["draft", "cancelled"]:
                raise ValidationError(_("Only draft or cancelled can be deleted"))
        return super().unlink()