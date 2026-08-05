from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    delivery_address_id = fields.Many2one("world.depot.delivery.address", string="Delivery Address", copy=False, index=True)

    @api.constrains("unload_company", "delivery_address_id")
    def check_delivery_address_recipient(self):
        for record in self:
            if record.delivery_address_id and record.delivery_address_id.recipient_id != record.unload_company:
                raise ValidationError(_("The delivery address must belong to the recipient."))

    @api.onchange("unload_company")
    def onchange_unload_company_delivery_address(self):
        for record in self:
            if not record.unload_company:
                record.delivery_address_id = False
                record.update({
                    "delivery_street": False,
                    "delivery_city": False,
                    "delivery_zip": False,
                    "delivery_country_id": False,
                    "delivery_phone": False,
                    "delivery_mobile": False,
                    "delivery_email": False,
                })
                continue

            address_records = record.env["world.depot.delivery.address"].sudo().search([
                ("recipient_id", "=", record.unload_company.id),
                ("active", "=", True),
            ], limit=2)
            if len(address_records) == 1:
                record.delivery_address_id = address_records
                record.set_delivery_address_snapshot()
            else:
                record.delivery_address_id = False
                record.update({
                    "delivery_street": False,
                    "delivery_city": False,
                    "delivery_zip": False,
                    "delivery_country_id": False,
                    "delivery_phone": False,
                    "delivery_mobile": False,
                    "delivery_email": False,
                })

    @api.onchange("delivery_address_id")
    def onchange_delivery_address_id(self):
        warning = False
        for record in self:
            if not record.delivery_address_id:
                continue
            if record.delivery_address_id.recipient_id != record.unload_company:
                record.delivery_address_id = False
                warning = _("The delivery address must belong to the recipient.")
                continue
            record.set_delivery_address_snapshot()
        if warning:
            return {"warning": {"title": _("Invalid Delivery Address"), "message": warning}}

    def set_delivery_address_snapshot(self):
        for record in self:
            if not record.delivery_address_id:
                continue
            record.delivery_street = record.delivery_address_id.street
            record.delivery_city = record.delivery_address_id.city
            record.delivery_zip = record.delivery_address_id.zip
            record.delivery_country_id = record.delivery_address_id.country_id
            record.delivery_phone = record.delivery_address_id.phone
            record.delivery_mobile = record.delivery_address_id.mobile
            record.delivery_email = record.delivery_address_id.email

    def action_open_delivery_address_wizard(self):
        if len(self) != 1:
            raise UserError(_("Select one outbound order."))
        for record in self:
            if record.state == "cancel":
                raise UserError(_("A cancelled outbound order cannot be changed."))
            if not record.unload_company:
                raise UserError(_("Select a recipient before selecting a delivery address."))

            address_records = record.env["world.depot.delivery.address"].sudo().search([
                ("recipient_id", "=", record.unload_company.id),
                ("active", "=", True),
            ], limit=2)
            default_address_id = False
            if record.delivery_address_id.recipient_id == record.unload_company:
                default_address_id = record.delivery_address_id.id
            default_address_mode = "new"
            if default_address_id:
                default_address_mode = "existing"
            elif len(address_records) == 1:
                default_address_id = address_records.id
                default_address_mode = "existing"
            elif address_records:
                default_address_mode = "existing"
            return {
                "type": "ir.actions.act_window",
                "name": _("Select Delivery Address"),
                "res_model": "world.depot.delivery.address.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_outbound_order_id": record.id,
                    "default_recipient_id": record.unload_company.id,
                    "default_address_id": default_address_id,
                    "default_address_mode": default_address_mode,
                },
            }
