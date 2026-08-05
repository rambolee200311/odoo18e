import re

from odoo import api, fields, models


def build_address_key(street, city, zip_code, country_code):
    values = [street or "", city or "", zip_code or "", country_code or ""]
    return "|".join(re.sub(r"[\W_]+", "", value.casefold()) for value in values)


class WorldDepotDeliveryAddress(models.Model):
    _name = "world.depot.delivery.address"
    _description = "World Depot Delivery Address"
    _rec_name = "name"
    _order = "id desc"

    name = fields.Char(string="Address", compute="_compute_name", store=True, index=True)
    address_key = fields.Char(string="Address Key", compute="_compute_address_key", store=True, index=True)
    active = fields.Boolean(string="Active", default=True)
    recipient_id = fields.Many2one("res.partner", string="Recipient", required=True, ondelete="cascade", index=True)
    street = fields.Char(string="Street", required=True)
    city = fields.Char(string="City")
    zip = fields.Char(string="ZIP")
    country_id = fields.Many2one("res.country", string="Country")
    phone = fields.Char(string="Phone")
    mobile = fields.Char(string="Mobile")
    email = fields.Char(string="Email")

    @api.depends("street", "city", "zip", "country_id")
    def _compute_name(self):
        for record in self:
            city_line = " ".join(part for part in [record.zip, record.city] if part)
            record.name = ", ".join(part for part in [record.street, city_line, record.country_id.name] if part)

    @api.depends("street", "city", "zip", "country_id")
    def _compute_address_key(self):
        for record in self:
            record.address_key = build_address_key(record.street, record.city, record.zip, record.country_id.code)


class ResPartner(models.Model):
    _inherit = "res.partner"

    delivery_address_ids = fields.One2many("world.depot.delivery.address", "recipient_id", string="Delivery Addresses")
