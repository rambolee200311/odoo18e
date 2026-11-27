# -*- coding: utf-8 -*-

from odoo import _, models


class VasOrder(models.Model):
    _inherit = "wd.vas.order"

    def action_submit(self):
        result = super().action_submit()
        self.sync_outbound_warehouse_operation_charges()
        self.sync_inbound_warehouse_operation_charges()
        return result

    def sync_inbound_warehouse_operation_charges(self):
        env_charge = self.env["world.depot.inbound.order.charge"]
        env_quotation_line = self.env["charge.quotation.line"]
        for rec in self:
            source_rec = rec.sudo()
            if source_rec.state != "submitted" or source_rec.order_type != "inbound" or not source_rec.inbound_order_id:
                continue
            work_lines = source_rec.line_ids.filtered(lambda line: not line.operation_type_id.is_outbound_palletization and line.operation_type_id.charge_item_id)
            existing_charge_lines = env_charge.browse(env_charge.sudo().search([("vas_order_id", "=", rec.id)]).ids)
            existing_charge_by_vas_line_id = {line.vas_order_line_id.id: line for line in existing_charge_lines}
            work_line_ids = set(work_lines.ids)
            existing_charge_lines.filtered(lambda line: line.vas_order_line_id.id not in work_line_ids).unlink()
            quotation = source_rec.inbound_order_id.project.quotation_id
            quotation_lines = env_quotation_line.sudo().search([("quotation_id", "=", quotation.id), ("tab_category", "=", "warehouse_operation"), ("active", "=", True)]) if quotation else env_quotation_line
            for work_line in work_lines:
                charge_item = work_line.operation_type_id.charge_item_id
                quotation_line = quotation_lines.filtered(lambda line: line.charge_item_id == charge_item)[:1]
                values = {"inbound_order_id": source_rec.inbound_order_id.id, "charge_item_id": charge_item.id, "quantity": work_line.quantity_time, "charge_unit_id": charge_item.unit_id.id, "unit_price": quotation_line.unit_price if quotation_line else 0.0, "currency_id": quotation.currency_id.id if quotation_line else source_rec.inbound_order_id.currency_id.id, "description": work_line.note or _("Generated from warehouse work order %s") % source_rec.name, "quotation_id": quotation.id if quotation_line else False, "quotation_line_id": quotation_line.id, "is_warehouse_operation_charge": True, "vas_order_id": rec.id, "vas_order_line_id": work_line.id}
                existing_charge_line = existing_charge_by_vas_line_id.get(work_line.id)
                if existing_charge_line:
                    existing_charge_line.write(values)
                else:
                    env_charge.create(values)

    def sync_outbound_warehouse_operation_charges(self):
        env_charge = self.env["world.depot.outbound.order.charge"]
        env_quotation_line = self.env["charge.quotation.line"]
        for rec in self:
            source_rec = rec.sudo()
            if source_rec.state != "submitted" or source_rec.order_type != "outbound" or not source_rec.outbound_order_id:
                continue
            work_lines = source_rec.line_ids.filtered(lambda line: not line.operation_type_id.is_outbound_palletization and line.operation_type_id.charge_item_id)
            existing_charge_lines = env_charge.browse(env_charge.sudo().search([("vas_order_id", "=", rec.id)]).ids)
            existing_charge_by_vas_line_id = {line.vas_order_line_id.id: line for line in existing_charge_lines}
            work_line_ids = set(work_lines.ids)
            existing_charge_lines.filtered(lambda line: line.vas_order_line_id.id not in work_line_ids).unlink()
            quotation = source_rec.outbound_order_id.project.quotation_id
            quotation_lines = env_quotation_line.sudo().search([
                ("quotation_id", "=", quotation.id), ("tab_category", "=", "warehouse_operation"), ("active", "=", True),
            ]) if quotation else env_quotation_line
            for work_line in work_lines:
                charge_item = work_line.operation_type_id.charge_item_id
                quotation_line = quotation_lines.filtered(lambda line: line.charge_item_id == charge_item)[:1]
                values = {
                    "outbound_order_id": source_rec.outbound_order_id.id, "charge_item_id": charge_item.id, "quantity": work_line.quantity_time,
                    "charge_unit_id": charge_item.unit_id.id, "unit_price": quotation_line.unit_price if quotation_line else 0.0,
                    "currency_id": quotation.currency_id.id if quotation_line else source_rec.outbound_order_id.currency_id.id,
                    "description": work_line.note or _("Generated from warehouse work order %s") % source_rec.name,
                    "quotation_id": quotation.id if quotation_line else False, "quotation_line_id": quotation_line.id,
                    "is_warehouse_operation_charge": True, "vas_order_id": rec.id, "vas_order_line_id": work_line.id,
                }
                existing_charge_line = existing_charge_by_vas_line_id.get(work_line.id)
                if existing_charge_line:
                    existing_charge_line.write(values)
                else:
                    env_charge.create(values)
