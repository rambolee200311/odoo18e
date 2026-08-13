import json
import logging

import requests

from odoo import _, fields, models, api
from odoo.exceptions import UserError

from ..models.delivery_address import build_address_key

_logger = logging.getLogger(__name__)


class WorldDepotDeliveryAddressWizard(models.TransientModel):
    _name = "world.depot.delivery.address.wizard"
    _description = "World Depot Delivery Address Wizard"

    outbound_order_id = fields.Many2one("world.depot.outbound.order", string="Outbound Order", required=True, readonly=True)
    raw_text = fields.Text(string="Google Address Text")
    is_parsed = fields.Boolean(string="Parsed", default=False, readonly=True)
    parsed_recipient_name = fields.Char(string="Parsed Recipient", readonly=True)
    recipient_id = fields.Many2one("res.partner", string="Recipient", required=True, readonly=True)
    address_mode = fields.Selection([("existing", "Use Saved Address"), ("new", "Save Parsed Address")], string="Address Handling", required=True, default="new")
    address_id = fields.Many2one("world.depot.delivery.address", string="Saved Delivery Address")
    street = fields.Char(string="Street")
    city = fields.Char(string="City")
    zip = fields.Char(string="ZIP")
    country_id = fields.Many2one("res.country", string="Country")
    phone = fields.Char(string="Phone")
    mobile = fields.Char(string="Mobile")
    email = fields.Char(string="Email")

    def set_saved_address_snapshot(self):
        for record in self:
            if not record.address_id:
                continue

            address = record.address_id
            record.update({
                "street": address.street,
                "city": address.city,
                "zip": address.zip,
                "country_id": address.country_id.id,
                "phone": address.phone,
                "mobile": address.mobile,
                "email": address.email,
            })

    @api.onchange("address_id")
    def onchange_address_id(self):
        for record in self:
            if record.address_id:
                record.set_saved_address_snapshot()
    def set_matched_delivery_address(self):
        for record in self:
            record.write({"address_mode": "new", "address_id": False})
            if not all([record.street, record.city, record.zip, record.country_id]):
                continue

            address_key = build_address_key(record.street, record.city, record.zip, record.country_id.code)
            address_records = record.env["world.depot.delivery.address"].sudo().search([
                ("recipient_id", "=", record.recipient_id.id),
                ("address_key", "=", address_key),
                ("active", "=", True),
            ], limit=2)
            if len(address_records) == 1:
                record.write({"address_mode": "existing", "address_id": address_records.id})
                record.set_saved_address_snapshot()
            elif address_records:
                record.write({"address_mode": "existing", "address_id": False})

    def get_wizard_form_action(self):
        action = False
        for record in self:
            action = {
                "type": "ir.actions.act_window",
                "name": _("Select Delivery Address"),
                "res_model": "world.depot.delivery.address.wizard",
                "view_mode": "form",
                "res_id": record.id,
                "target": "new",
            }
        return action

    def action_parse_delivery_text(self):

        for record in self:

            if not record.raw_text or not record.raw_text.strip():
                raise UserError(_("Paste an address before parsing."))
            if len(record.raw_text.strip()) > 1000:
                raise UserError(_("Google address text cannot exceed 1,000 characters."))

            google_maps_key = record.env["ir.config_parameter"].sudo().get_param("google_maps_api_key")
            if not google_maps_key:
                raise UserError(_("Google Maps API key is not configured."))

            try:
                google_response = requests.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={"address": record.raw_text.strip(), "key": google_maps_key},
                    timeout=(10, 30),
                )
            except requests.RequestException as error:
                raise UserError(_("Google address parsing request failed: %s") % error) from error

            if not google_response.ok:
                raise UserError(_("Google address parsing failed with status %s.") % google_response.status_code)

            try:
                google_values = google_response.json()
                if google_values.get("status") != "OK" or not google_values.get("results"):
                    raise UserError(_("Google could not find a matching address (%s).") % google_values.get("status", "UNKNOWN_ERROR"))
                components = {}
                for component in google_values["results"][0].get("address_components", []):
                    for component_type in component.get("types", []):
                        components[component_type] = component
            except (ValueError, KeyError, IndexError, TypeError) as error:
                raise UserError(_("Google did not return a valid address result.")) from error

            street = " ".join(part for part in [
                components.get("street_number", {}).get("long_name"),
                components.get("route", {}).get("long_name"),
            ] if part)
            city = (
                components.get("locality", {}).get("long_name")
                or components.get("postal_town", {}).get("long_name")
                or components.get("administrative_area_level_2", {}).get("long_name")
            )
            country_code = components.get("country", {}).get("short_name")
            country = record.env["res.country"].sudo().search([("code", "=", country_code)], limit=1) if country_code else False
            record.write({
                "is_parsed": True,
                "parsed_recipient_name": False,
                "street": street,
                "city": city,
                "zip": components.get("postal_code", {}).get("long_name"),
                "country_id": country.id,
            })
            record.set_matched_delivery_address()
        return self.get_wizard_form_action()

    def action_parse_delivery_text_with_deepseek(self):
        for record in self:
            if not record.raw_text or not record.raw_text.strip():
                raise UserError(_("Paste delivery text before parsing."))
            if len(record.raw_text.strip()) > 5000:
                raise UserError(_("Pasted delivery text cannot exceed 5,000 characters."))

            config_model = record.env["ir.config_parameter"].sudo()
            api_key = config_model.get_param("deepseek.api_key")
            api_base = config_model.get_param("deepseek.api_base", "https://api.deepseek.com")
            model_name = config_model.get_param("deepseek.address_parse_model", "deepseek-v4-flash")
            if not api_key:
                raise UserError(_("DeepSeek API key is not configured."))

            payload = {
                "model": model_name,
                "thinking": {"type": "disabled"},
                "temperature": 0,
                "max_tokens": 300,
                "stream": False,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Parse European delivery contact text. Return one valid JSON object only. "
                            "Do not invent values. Use null when absent. "
                            "The JSON keys are recipient_name, phone, mobile, email, street, city, zip, country_code. "
                            "country_code must be ISO 3166-1 alpha-2."
                        ),
                    },
                    {"role": "user", "content": record.raw_text.strip()},
                ],
            }

            try:
                response = requests.post(
                    "%s/chat/completions" % api_base.rstrip("/"),
                    headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=(10, 60),
                )
            except requests.RequestException as error:
                raise UserError(_("DeepSeek address parsing request failed: %s") % error) from error

            if response.status_code != 200:
                raise UserError(_("DeepSeek address parsing failed with status %s.") % response.status_code)

            try:
                response_values = response.json()
                content = response_values["choices"][0]["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                parsed_values = json.loads(content)
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise UserError(_("DeepSeek did not return a valid JSON address result.")) from error

            country_code = str(parsed_values.get("country_code") or "").strip().upper()
            country = record.env["res.country"].sudo().search([("code", "=", country_code)], limit=1) if country_code else False
            record.write({
                "is_parsed": True,
                "parsed_recipient_name": str(parsed_values.get("recipient_name") or "").strip(),
                "street": str(parsed_values.get("street") or "").strip(),
                "city": str(parsed_values.get("city") or "").strip(),
                "zip": str(parsed_values.get("zip") or "").strip(),
                "country_id": country.id,
                "phone": str(parsed_values.get("phone") or "").strip(),
                "mobile": str(parsed_values.get("mobile") or "").strip(),
                "email": str(parsed_values.get("email") or "").strip(),
            })
            record.set_matched_delivery_address()
        return self.get_wizard_form_action()

    def action_apply_delivery_address(self):
        for record in self:
            if record.outbound_order_id.state == "cancel":
                raise UserError(_("A cancelled outbound order cannot be changed."))

            address_model = record.env["world.depot.delivery.address"]
            if record.address_mode == "existing":
                delivery_address = address_model.sudo().search([
                    ("id", "=", record.address_id.id),
                    ("recipient_id", "=", record.recipient_id.id),
                    ("active", "=", True),
                ], limit=1)
                if not delivery_address:
                    raise UserError(_("Select a saved address belonging to the recipient."))
            else:
                if not all([record.street, record.city, record.zip, record.country_id]):
                    raise UserError(_("Street, city, ZIP, and country are required for a new delivery address."))

                address_key = build_address_key(record.street, record.city, record.zip, record.country_id.code)
                delivery_address = address_model.sudo().search([
                    ("recipient_id", "=", record.recipient_id.id),
                    ("address_key", "=", address_key),
                    ("active", "=", True),
                ], limit=2)
                if len(delivery_address) > 1:
                    raise UserError(_("Multiple saved addresses match the parsed address. Select one saved address."))
                if not delivery_address:
                    delivery_address = address_model.create({
                        "recipient_id": record.recipient_id.id,
                        "street": record.street,
                        "city": record.city,
                        "zip": record.zip,
                        "country_id": record.country_id.id,
                        "phone": record.phone,
                        "mobile": record.mobile,
                        "email": record.email,
                    })

            record.outbound_order_id.write({
                "unload_company": record.recipient_id.id,
                "delivery_address_id": delivery_address.id,
                "delivery_street": delivery_address.street,
                "delivery_city": delivery_address.city,
                "delivery_zip": delivery_address.zip,
                "delivery_country_id": delivery_address.country_id.id,
                "delivery_phone": delivery_address.phone,
                "delivery_mobile": delivery_address.mobile,
                "delivery_email": delivery_address.email,
            })
        return {"type": "ir.actions.act_window_close"}
