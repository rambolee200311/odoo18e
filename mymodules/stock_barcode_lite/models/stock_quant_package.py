# -*- coding: utf-8 -*-

import uuid
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"
    _sql_constraints = [
        ("barcode_unique", "unique(barcode)", "Barcode must be unique."),
    ]

    billno = fields.Char(string="Bill No", copy=False)
    reference = fields.Char(string="Reference", copy=False)
    cntr_no = fields.Char(string="Container No", copy=False)
    barcode = fields.Char(string="Barcode", copy=False, index=True)
    original_pallet_no = fields.Char(string="Original Pallet No", copy=False, index=True)
    lifecycle_state = fields.Selection([("active", "Active"), ("consumed", "Consumed"), ("closed", "Closed")], string="Sunrise Lifecycle State", readonly=True, copy=False, index=True)
    lifecycle_start_datetime = fields.Datetime(string="Lifecycle Start At", readonly=True, copy=False, index=True)
    consumed_datetime = fields.Datetime(string="Consumed At", readonly=True, copy=False, index=True)

    @api.model
    def cron_backfill_sunrise_package_lifecycle(self):
        package_ids = self.sudo().search([
            ("lifecycle_state", "!=", "closed"),
            "|", "|",
            ("lifecycle_state", "=", False),
            ("lifecycle_start_datetime", "=", False),
            "&", ("lifecycle_state", "=", "consumed"), ("consumed_datetime", "=", False),
        ], order="id asc").ids
        if not package_ids:
            return True

        move_line_model = self.env["stock.move.line"].sudo()
        quant_model = self.env["stock.quant"].sudo()
        inbound_move_lines = move_line_model.search([
            ("move_id.state", "=", "done"),
            ("picking_id.picking_type_id.code", "=", "incoming"),
            ("picking_id.inbound_order_id.project.name", "=", "SUNRISE"),
            ("result_package_id", "in", package_ids),
        ])
        sunrise_package_ids = inbound_move_lines.mapped("result_package_id").ids
        if not sunrise_package_ids:
            return True

        move_lines = move_line_model.search([
            ("move_id.state", "=", "done"),
            "|", ("package_id", "in", sunrise_package_ids), ("result_package_id", "in", sunrise_package_ids),
        ], order="date asc, id asc")
        package_event_map = defaultdict(list)
        for move_line in move_lines:
            source_usage = move_line.location_id.usage
            destination_usage = move_line.location_dest_id.usage
            package = False
            signed_quantity = 0.0
            if source_usage == "inventory" and destination_usage == "internal":
                package = move_line.result_package_id or move_line.package_id
                signed_quantity = move_line.quantity
            elif source_usage == "internal" and destination_usage == "inventory":
                package = move_line.package_id or move_line.result_package_id
                signed_quantity = -move_line.quantity
            elif source_usage != "internal" and destination_usage == "internal":
                package = move_line.result_package_id or move_line.package_id
                signed_quantity = move_line.quantity
            elif source_usage == "internal" and destination_usage != "internal":
                package = move_line.package_id or move_line.result_package_id
                signed_quantity = -move_line.quantity
            if package and package.id in sunrise_package_ids and signed_quantity:
                package_event_map[package.id].append((move_line, signed_quantity))

        current_stock_package_ids = set(quant_model.search([
            ("package_id", "in", sunrise_package_ids),
            ("location_id.usage", "=", "internal"),
            ("quantity", ">", 0),
        ]).mapped("package_id").ids)
        for rec in self.browse(sunrise_package_ids):
            product_lot_quantity_map = defaultdict(float)
            lifecycle_start_datetime = False
            consumed_datetime = False
            for move_line, signed_quantity in package_event_map[rec.id]:
                before_active = any(quantity > 0.000001 for quantity in product_lot_quantity_map.values())
                quantity_key = (move_line.product_id.id, move_line.lot_id.id)
                product_lot_quantity_map[quantity_key] += signed_quantity
                after_active = any(quantity > 0.000001 for quantity in product_lot_quantity_map.values())
                if not before_active and after_active:
                    if not lifecycle_start_datetime:
                        lifecycle_start_datetime = move_line.date
                    consumed_datetime = False
                elif before_active and not after_active:
                    consumed_datetime = move_line.date

            values = {}
            if lifecycle_start_datetime and not rec.lifecycle_start_datetime:
                values["lifecycle_start_datetime"] = lifecycle_start_datetime
            if rec.id in current_stock_package_ids:
                if rec.lifecycle_state != "active":
                    values["lifecycle_state"] = "active"
            elif lifecycle_start_datetime:
                if rec.lifecycle_state != "consumed":
                    values["lifecycle_state"] = "consumed"
                if consumed_datetime and not rec.consumed_datetime:
                    values["consumed_datetime"] = consumed_datetime
            if values:
                rec.write(values)
        return True

    @api.model
    def generate_sunrise_package_barcode(self):
        """Return an unused eight-character barcode for a Sunrise package."""
        for _attempt in range(20):
            barcode = uuid.uuid4().hex[:8].upper()
            if not self.sudo().search([("barcode", "=", barcode)], limit=1):
                return barcode
        raise UserError(_("Could not generate a unique Sunrise package barcode."))
