# -*- coding: utf-8 -*-

import base64
import io

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StatementPeriod(models.Model):
    _inherit = "statement.period"

    outbound_order_lines = fields.One2many("world.depot.outbound.order", "statement_period_id", string="Outbound Orders")
    outbound_total_amount = fields.Monetary(string="Total Outbound Amount", currency_field="currency_id", compute="_compute_outbound_total_amount", store=True)

    @api.depends("outbound_order_lines.total_amount", "outbound_order_lines.manual_amount_total")
    def _compute_outbound_total_amount(self):
        for rec in self:
            rec.outbound_total_amount = sum(
                outbound_order.manual_amount_total if outbound_order.manual_amount_total > 0 else outbound_order.total_amount
                for outbound_order in rec.outbound_order_lines)

    def get_periodic_statement(self):
        for rec in self:
            if rec.state != "draft":
                raise ValidationError(_("Only draft statement periods can be generated."))
        result = super().get_periodic_statement()
        outbound_order_model = self.env["world.depot.outbound.order"]
        for rec in self:
            rec.outbound_order_lines = [(5, 0, 0)]
            outbound_time_field = "o_date" if getattr(rec.project_id, "stock_report_date_mode", "validation") == "business" else "picking_Out_date"
            outbound_orders = outbound_order_model.sudo().search([
                ("receivable_state", "=", "confirmed"),
                ("project", "=", rec.project_id.id),
                (outbound_time_field, ">=", rec.date_start),
                (outbound_time_field, "<=", rec.date_end),
            ])
            outbound_orders = self.env["world.depot.outbound.order"].browse(outbound_orders.ids)
            outbound_orders._compute_project_stock_report_date_mode()
            outbound_orders._compute_statement_outbound_date()
            rec.outbound_order_lines = [(6, 0, outbound_orders.ids)]
        return result

    def action_export_statement_xlsx(self):
        for rec in self:
            if rec.state == "draft":
                raise ValidationError(_("Please confirm the expense first."))
            output = io.BytesIO()
            wb = xlsxwriter.Workbook(output, {"in_memory": True})
            formats = self.get_xlsx_formats(wb)
            self.build_handover_sheet(wb, rec, formats)
            self.build_clearance_sheet(wb, rec, formats)
            self.build_outbound_sheet(wb, rec, formats)
            wb.close()
            output.seek(0)
            content = base64.b64encode(output.read())
            filename = f"Statement-{rec.name or rec.id}.xlsx"
            attachment = self.env["ir.attachment"].create({
                "name": filename,
                "type": "binary",
                "datas": content,
                "res_model": rec._name,
                "res_id": rec.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
            return {"type": "ir.actions.act_url", "url": f"/web/content/{attachment.id}?download=true", "target": "self"}

    def build_outbound_sheet(self, wb, rec, fmt):
        ws = wb.add_worksheet("Outbound")
        fixed_left = ["Outbound No", "Outbound Time"]
        fee_names = set()
        for outbound_order in rec.outbound_order_lines:
            for charge_line in outbound_order.outbound_order_charge_ids:
                if charge_line.charge_item_id and charge_line.charge_item_id.item_name:
                    fee_names.add(charge_line.charge_item_id.item_name)
        fee_cols = sorted(fee_names)
        headers = fixed_left + fee_cols + ["Amount"]
        ws.set_column(0, 0, 22)
        ws.set_column(1, 1, 14)
        fee_start = len(fixed_left)
        if fee_cols:
            ws.set_column(fee_start, fee_start + len(fee_cols) - 1, 18)
        amount_col = len(headers) - 1
        ws.set_column(amount_col, amount_col, 16)
        ws.write_row(0, 0, headers, fmt["header"])
        row = 1
        for outbound_order in rec.outbound_order_lines:
            ws.write(row, 0, outbound_order.billno or "", fmt["cell"])
            if getattr(rec.project_id, "stock_report_date_mode", "validation") == "business":
                outbound_time = outbound_order.o_date.strftime("%Y-%m-%d") if outbound_order.o_date else ""
            else:
                outbound_time = fields.Datetime.context_timestamp(outbound_order, outbound_order.picking_Out_date).strftime("%Y-%m-%d %H:%M:%S") if outbound_order.picking_Out_date else ""
            ws.write(row, 1, outbound_time, fmt["cell"])
            for index, fee_name in enumerate(fee_cols):
                charge_lines = outbound_order.outbound_order_charge_ids.filtered(
                    lambda charge_line: charge_line.charge_item_id and charge_line.charge_item_id.item_name == fee_name)
                ws.write_number(row, fee_start + index, float(sum(charge_lines.mapped("amount"))), fmt["money"])
            line_total = outbound_order.manual_amount_total if outbound_order.manual_amount_total > 0 else outbound_order.total_amount
            ws.write_number(row, amount_col, float(line_total or 0.0), fmt["money"])
            row += 1
        ws.merge_range(row, 0, row, amount_col - 1, "Total amount", fmt["total_label"])
        ws.write_number(row, amount_col, float(rec.outbound_total_amount or 0.0), fmt["total_money"])
