import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


def build_delivery_address_key(street, street2, city, zip_code, state_code, country_code):
    values = [street or "", street2 or "", city or "", zip_code or "", state_code or "", country_code or ""]
    return "|".join(re.sub(r"[\W_]+", "", str(value).casefold()) for value in values)


class ResPartner(models.Model):
    _inherit = "res.partner"

    delivery_address_key = fields.Char(string="Delivery Address Key", compute="_compute_delivery_address_key", store=True, index=True, copy=False)

    @api.depends("parent_id", "type", "street", "street2", "city", "zip", "state_id", "country_id")
    def _compute_delivery_address_key(self):
        for record in self:
            if record.type != "delivery" or not record.parent_id or not record.street:
                record.delivery_address_key = False
                continue
            record.delivery_address_key = build_delivery_address_key(
                record.street,
                record.street2,
                record.city,
                record.zip,
                record.state_id.code,
                record.country_id.code,
            )

    @api.constrains("parent_id", "type", "delivery_address_key")
    def check_delivery_address_duplicate(self):
        partner_model = self.env["res.partner"]
        for record in self:
            if record.type != "delivery" or not record.parent_id or not record.delivery_address_key:
                continue
            duplicate_partner = partner_model.with_context(active_test=False).sudo().search([
                ("id", "!=", record.id),
                ("parent_id", "=", record.parent_id.id),
                ("type", "=", "delivery"),
                ("delivery_address_key", "=", record.delivery_address_key),
            ], limit=1)
            if duplicate_partner:
                raise ValidationError(_("This delivery address already exists for the customer."))

    def get_delivery_partner_from_values(self, address_values, create_missing=True):
        partner_model = self.env["res.partner"]
        country_model = self.env["res.country"]
        state_model = self.env["res.country.state"]
        delivery_partners = partner_model
        for record in self:
            street = str(address_values.get("street") or "").strip()
            street2 = str(address_values.get("street2") or "").strip()
            city = str(address_values.get("city") or "").strip()
            zip_code = str(address_values.get("zip") or "").strip()
            phone = str(address_values.get("phone") or "").strip()
            mobile = str(address_values.get("mobile") or "").strip()
            email = str(address_values.get("email") or "").strip()
            country_id = getattr(address_values.get("country_id"), "id", address_values.get("country_id")) or False
            state_id = getattr(address_values.get("state_id"), "id", address_values.get("state_id")) or False
            if not street:
                if create_missing:
                    raise ValidationError(_("Street is required for a delivery address."))
                continue
            country = country_model.sudo().browse(country_id)
            state = state_model.sudo().browse(state_id)
            address_key = build_delivery_address_key(street, street2, city, zip_code, state.code, country.code)
            recipient_key = build_delivery_address_key(
                record.street,
                record.street2,
                record.city,
                record.zip,
                record.state_id.code,
                record.country_id.code,
            )
            if record.active and address_key == recipient_key:
                delivery_partners |= record
                continue
            delivery_partner_sudo = partner_model.with_context(active_test=False).sudo().search([
                ("parent_id", "=", record.id),
                ("type", "=", "delivery"),
                ("delivery_address_key", "=", address_key),
            ], limit=1)
            if delivery_partner_sudo:
                delivery_partner = partner_model.browse(delivery_partner_sudo.id)
                if not delivery_partner.active:
                    delivery_partner.write({"active": True})
                delivery_partners |= delivery_partner
                continue
            if not create_missing:
                continue
            delivery_partners |= partner_model.create({
                "name": str(address_values.get("name") or street).strip(),
                "parent_id": record.id,
                "type": "delivery",
                "street": street,
                "street2": street2,
                "city": city,
                "zip": zip_code,
                "state_id": state_id,
                "country_id": country_id,
                "phone": phone,
                "mobile": mobile,
                "email": email,
            })
        return delivery_partners


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    delivery_partner_id = fields.Many2one("res.partner", string="Delivery Address", copy=False, index=True)

    def clear_delivery_partner_snapshot(self):
        for record in self:
            record.update({
                "delivery_street": False,
                "delivery_city": False,
                "delivery_zip": False,
                "delivery_country_id": False,
                "delivery_phone": False,
                "delivery_mobile": False,
                "delivery_email": False,
            })

    @api.constrains("unload_company", "delivery_partner_id")
    def check_delivery_partner_recipient(self):
        for record in self:
            delivery_partner = record.delivery_partner_id
            if not delivery_partner:
                continue
            is_recipient_address = delivery_partner == record.unload_company
            is_delivery_child = bool(record.unload_company) and delivery_partner.parent_id == record.unload_company and delivery_partner.type == "delivery"
            has_delivery_street = bool(delivery_partner.street)
            if not delivery_partner.active or not has_delivery_street or not (is_recipient_address or is_delivery_child):
                raise ValidationError(_("The delivery address must be an active recipient address or delivery address with a street."))

    @api.onchange("unload_company")
    def onchange_unload_company_delivery_partner(self):
        for record in self:
            delivery_partner = record.delivery_partner_id
            is_recipient_address = delivery_partner == record.unload_company
            is_delivery_child = bool(record.unload_company) and delivery_partner.parent_id == record.unload_company and delivery_partner.type == "delivery"
            has_delivery_street = bool(delivery_partner.street)
            if record.unload_company and delivery_partner and delivery_partner.active and has_delivery_street and (is_recipient_address or is_delivery_child):
                record.set_delivery_partner_snapshot()
                continue
            record.delivery_partner_id = False
            record.clear_delivery_partner_snapshot()

    @api.onchange("delivery_partner_id")
    def onchange_delivery_partner_id(self):
        warning = False
        for record in self:
            delivery_partner = record.delivery_partner_id
            if not delivery_partner:
                record.clear_delivery_partner_snapshot()
                continue
            is_recipient_address = delivery_partner == record.unload_company
            is_delivery_child = bool(record.unload_company) and delivery_partner.parent_id == record.unload_company and delivery_partner.type == "delivery"
            has_delivery_street = bool(delivery_partner.street)
            if not delivery_partner.active or not has_delivery_street or not (is_recipient_address or is_delivery_child):
                record.delivery_partner_id = False
                record.clear_delivery_partner_snapshot()
                warning = _("The delivery address must be an active recipient address or delivery address with a street.")
                continue
            record.set_delivery_partner_snapshot()
        if warning:
            return {"warning": {"title": _("Invalid Delivery Address"), "message": warning}}

    def set_delivery_partner_snapshot(self):
        for record in self:
            if not record.delivery_partner_id:
                continue
            record.update({
                "delivery_street": record.delivery_partner_id.street,
                "delivery_city": record.delivery_partner_id.city,
                "delivery_zip": record.delivery_partner_id.zip,
                "delivery_country_id": record.delivery_partner_id.country_id.id,
                "delivery_phone": record.delivery_partner_id.phone,
                "delivery_mobile": record.delivery_partner_id.mobile,
                "delivery_email": record.delivery_partner_id.email,
            })

    def action_open_delivery_address_wizard(self):
        if len(self) != 1:
            raise UserError(_("Select one outbound order."))
        for record in self:
            if record.state == "cancel":
                raise UserError(_("A cancelled outbound order cannot be changed."))
            if not record.unload_company:
                raise UserError(_("Select a recipient before selecting a delivery address."))
            delivery_partner = record.delivery_partner_id
            is_recipient_address = delivery_partner == record.unload_company
            is_delivery_child = bool(record.unload_company) and delivery_partner.parent_id == record.unload_company and delivery_partner.type == "delivery"
            has_delivery_street = bool(delivery_partner.street)
            default_delivery_partner_id = delivery_partner.id if delivery_partner.active and has_delivery_street and (is_recipient_address or is_delivery_child) else False
            return {
                "type": "ir.actions.act_window",
                "name": _("Select Delivery Address"),
                "res_model": "world.depot.delivery.address.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_outbound_order_id": record.id,
                    "default_recipient_id": record.unload_company.id,
                    "default_delivery_partner_id": default_delivery_partner_id,
                    "default_address_mode": "existing" if default_delivery_partner_id else "new",
                },
            }
