import time
from datetime import datetime, timedelta
import requests
import logging
from odoo import _, models, fields, api
from odoo.exceptions import UserError
from collections import defaultdict
from odoo.exceptions import ValidationError
WAYBILL_STATE = [('new', 'New'), ('confirm', 'Confirm'), ('done', 'Done'), ('cancel', 'Cancel')]

class Waybill(models.Model):
    _name = "world.depot.waybill"
    _description = "Waybill"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = 'bl_number'
    _order = "id DESC"

    billno = fields.Char(string='BillNo', readonly=True)
    project = fields.Many2one('project.project', string='Project', required=True, ondelete='cascade', )

    # ========== 基础信息 ==========
    bl_number = fields.Char(string='Bill of Lading',index=True)  # NKGA84065
    hbl_number = fields.Char(string='House Bill of Lading',index=True)  # HBL123456789
    search_bl_hbl = fields.Char(string="BL / HBL No", store=False)

    document_number = fields.Char(string='Document No')  # S2502461054/C2501146242
    reference_number = fields.Char(string='Reference No')  # SHPR REF: AB20250404336
    hs_code_qty = fields.Integer(string='HS Code Qty')
    # ========== 参与方信息 ==========
    shipping = fields.Many2one('res.partner', string='Shipping Line',
                               tracking=True)
    shipper = fields.Many2one('res.partner', string='Shipper/Exporter',
                              tracking=True)
    voyage_no = fields.Char(string="Voyage No.", index=True)
    consignee = fields.Many2one('res.partner', string='Consignee/Importer',
                                tracking=True)
    notify_party = fields.Many2one('res.partner', string='Notify',
                                   tracking=True)

    state = fields.Selection(
        selection=WAYBILL_STATE,
        default='new',
        string="State",
        tracking=True,
        group_expand=True
    )
    remark = fields.Text(string='Remark', tracking=True)

    eta = fields.Date(string='ETA', tracking=True)
    ata = fields.Date(string='ATA', tracking=True)
    terminal_port = fields.Many2one('res.partner', string='Terminal of Port', tracking=True)
    terminal_a = fields.Many2one('res.partner', string='Terminal of Arrival', tracking=True)

    release_received = fields.Boolean(string='Release Received', default=False, tracking=True)
    custom_clearance = fields.Boolean(string='Custom Clearance', default=False, tracking=True)

    other_docs_ids = fields.One2many('world.depot.waybill.other.docs', 'waybill_id', string='Other Documents',
                                     help='Other documents related to the waybill, such as invoices, packing lists, etc.')

    # 关联集装箱
    container_ids = fields.One2many('world.depot.waybill.container', 'waybill_id', string='Containers',
                                    help='Containers associated with this waybill')

    # 关联运单箱单
    packing_list_ids = fields.One2many('world.depot.waybill.packing.list', 'waybill_id', string='Packing Lists',
                                       help='Packing lists associated with this container')
    obl_number = fields.Char(string="OBL No")

    quotation_id = fields.Many2one("charge.quotation", string="Quotation", copy=False, index=True,
                                   tracking=True)
    quotation_effective_date = fields.Date(string="Quotation Effective Date", copy=False, index=True,
                                           tracking=True)
    container_qty = fields.Integer(string="Container Qty",compute="_compute_container_ids", tracking=True)

    handover_id = fields.Many2one("operation.order.handover", string="Handover")
    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance")
    handover_lines = fields.One2many("operation.order.handover", "waybill_id", string="Handovers", copy=False)
    clearance_lines = fields.One2many("operation.order.clearance", "waybill_id", string="Clearances", copy=False)
    handover_status = fields.Selection(related="handover_id.state", string="Handover Status", readonly=True)
    handover_receivable_state = fields.Selection(related="handover_id.receivable_state", string="Handover Receivable Status", readonly=True)
    handover_payable_state = fields.Selection([("not_applicable", "N/A"), ("not_applied", "Not Applied"), ("paying", "Paying"), ("paid", "Paid")], string="Handover Payable Status", compute="_compute_operation_fee_states", store=True, readonly=True, index=True)
    handover_receivable_summary_state = fields.Selection([("not_applicable", "N/A"), ("draft", "Unconfirmed"), ("confirmed", "Confirmed")], string="Handover Receivable Status", compute="_compute_operation_fee_states", store=True, readonly=True, index=True)
    handover_bl_release_type = fields.Selection(related="handover_id.bl_release_type", string="BL Release Type", readonly=False)
    handover_do_no = fields.Char(related="handover_id.do_no", string="Delivery Order No.", readonly=False)
    handover_remark = fields.Text(related="handover_id.remark", string="Handover Remark", readonly=False)
    handover_invoice_lines = fields.One2many(related="handover_id.invoice_line_ids", string="Handover Vendor Invoice Lines", readonly=False)
    handover_charge_lines = fields.One2many(related="handover_id.charge_line_ids", string="Handover Charge Lines", readonly=False)
    handover_container_lines = fields.One2many(related="handover_id.container_line_ids", string="Handover Containers", readonly=True)
    handover_is_overdue = fields.Boolean(related="handover_id.is_handover_overdue", string="Is Handover Overdue", readonly=True)
    handover_overdue_blocking_reason_id = fields.Many2one(related="handover_id.overdue_blocking_reason_id", string="Handover Overdue Blocking Reason", readonly=False)
    handover_overdue_blocking_reason_short_name = fields.Char(related="handover_id.overdue_blocking_reason_short_name", string="Handover Overdue Blocking Reason Short Name", readonly=True)
    handover_overdue_reason_note = fields.Text(related="handover_id.overdue_reason_note", string="Handover Overdue Reason Note", readonly=False)
    handover_overdue_handle_result = fields.Selection(related="handover_id.overdue_handle_result", string="Handover Overdue Handle Result", readonly=False)
    handover_overdue_result_note = fields.Text(related="handover_id.overdue_result_note", string="Handover Overdue Result Note", readonly=False)
    clearance_status = fields.Selection(related="clearance_id.state", string="Clearance Status", readonly=True)
    clearance_receivable_state = fields.Selection(related="clearance_id.receivable_state", string="Clearance Receivable Status", readonly=True)
    clearance_payable_state = fields.Selection([("not_applied", "Not Applied"), ("paying", "Paying"), ("paid", "Paid")], string="Clearance Payable Status", compute="_compute_operation_fee_states", store=True, readonly=True, index=True)
    clearance_receivable_summary_state = fields.Selection([("draft", "Unconfirmed"), ("confirmed", "Confirmed")], string="Clearance Receivable Status", compute="_compute_operation_fee_states", store=True, readonly=True, index=True)
    operation_fee_completed = fields.Boolean(string="Operation Fee Completed", compute="_compute_operation_fee_states", store=True, readonly=True, index=True)
    clearance_operation_type = fields.Selection(related="clearance_id.clearance_type", string="Clearance Type", readonly=False)
    clearance_receipt_no = fields.Char(related="clearance_id.clearance_receipt_no", string="Customs Clearance Receipt No.", readonly=False)
    clearance_hs_code_qty = fields.Integer(related="clearance_id.hs_code_qty", string="HS Code Qty", readonly=False)
    clearance_remark = fields.Text(related="clearance_id.remark", string="Clearance Remark", readonly=False)
    clearance_invoice_lines = fields.One2many(related="clearance_id.invoice_line_ids", string="Clearance Vendor Invoice Lines", readonly=False)
    clearance_charge_lines = fields.One2many(related="clearance_id.charge_line_ids", string="Clearance Charge Lines", readonly=False)
    clearance_container_line_ids = fields.Many2many(related="clearance_id.clearance_container_ids", string="Clearance Containers", readonly=True)
    clearance_is_overdue = fields.Boolean(related="clearance_id.is_clearance_overdue", string="Is Clearance Overdue", readonly=True)
    clearance_overdue_blocking_reason_id = fields.Many2one(related="clearance_id.overdue_blocking_reason_id", string="Clearance Overdue Blocking Reason", readonly=False)
    clearance_overdue_blocking_reason_short_name = fields.Char(related="clearance_id.overdue_blocking_reason_short_name", string="Clearance Overdue Blocking Reason Short Name", readonly=True)
    clearance_overdue_reason_note = fields.Text(related="clearance_id.overdue_reason_note", string="Clearance Overdue Reason Note", readonly=False)
    clearance_overdue_handle_result = fields.Selection(related="clearance_id.overdue_handle_result", string="Clearance Overdue Handle Result", readonly=False)
    clearance_overdue_result_note = fields.Text(related="clearance_id.overdue_result_note", string="Clearance Overdue Result Note", readonly=False)
    handover_child_lines = fields.One2many(related="handover_id.child_ids", string="Child Handovers", readonly=False)
    clearance_child_lines = fields.One2many(related="clearance_id.child_lines", string="Child Clearances", readonly=False)
    selected_child_handover_id = fields.Many2one("operation.order.handover", string="Selected Child Handover", copy=False, index=True)
    selected_child_handover_status = fields.Selection(related="selected_child_handover_id.state", string="Child Handover Status", readonly=True)
    selected_child_handover_payable_state = fields.Selection(related="selected_child_handover_id.payable_state", string="Child Handover Payable Status", readonly=True, store=True)
    selected_child_handover_receivable_state = fields.Selection(related="selected_child_handover_id.receivable_state", string="Child Handover Receivable Status", readonly=True)
    selected_child_handover_bl_release_type = fields.Selection(related="selected_child_handover_id.bl_release_type", string="Child BL Release Type", readonly=False)
    selected_child_handover_do_no = fields.Char(related="selected_child_handover_id.do_no", string="Child Delivery Order No.", readonly=False)
    selected_child_handover_extra_reason = fields.Selection(related="selected_child_handover_id.extra_reason", string="Child Additional Reason", readonly=False)
    selected_child_handover_extra_remark = fields.Char(related="selected_child_handover_id.extra_remark", string="Child Additional Remark", readonly=False)
    selected_child_handover_actual_datetime = fields.Datetime(related="selected_child_handover_id.actual_datetime", string="Child Actual Date", readonly=False)
    selected_child_handover_remark = fields.Text(related="selected_child_handover_id.remark", string="Child Handover Remark", readonly=False)
    selected_child_handover_invoice_lines = fields.One2many(related="selected_child_handover_id.invoice_line_ids", string="Child Handover Vendor Invoice Lines", readonly=False)
    selected_child_handover_charge_lines = fields.One2many(related="selected_child_handover_id.charge_line_ids", string="Child Handover Charge Lines", readonly=False)
    selected_child_handover_container_lines = fields.One2many(related="selected_child_handover_id.container_line_ids", string="Child Handover Containers", readonly=True)
    selected_child_handover_is_overdue = fields.Boolean(related="selected_child_handover_id.is_handover_overdue", string="Is Child Handover Overdue", readonly=True)
    selected_child_handover_overdue_blocking_reason_id = fields.Many2one(related="selected_child_handover_id.overdue_blocking_reason_id", string="Child Handover Overdue Blocking Reason", readonly=False)
    selected_child_handover_overdue_blocking_reason_short_name = fields.Char(related="selected_child_handover_id.overdue_blocking_reason_short_name", string="Child Handover Overdue Blocking Reason Short Name", readonly=True)
    selected_child_handover_overdue_reason_note = fields.Text(related="selected_child_handover_id.overdue_reason_note", string="Child Handover Overdue Reason Note", readonly=False)
    selected_child_handover_overdue_handle_result = fields.Selection(related="selected_child_handover_id.overdue_handle_result", string="Child Handover Overdue Handle Result", readonly=False)
    selected_child_handover_overdue_result_note = fields.Text(related="selected_child_handover_id.overdue_result_note", string="Child Handover Overdue Result Note", readonly=False)
    selected_child_clearance_id = fields.Many2one("operation.order.clearance", string="Selected Child Clearance", copy=False, index=True)
    selected_child_clearance_status = fields.Selection(related="selected_child_clearance_id.state", string="Child Clearance Status", readonly=True)
    selected_child_clearance_payable_state = fields.Selection(related="selected_child_clearance_id.payable_state", string="Child Clearance Payable Status", readonly=True, store=True)
    selected_child_clearance_receivable_state = fields.Selection(related="selected_child_clearance_id.receivable_state", string="Child Clearance Receivable Status", readonly=True)
    selected_child_clearance_operation_type = fields.Selection(related="selected_child_clearance_id.clearance_type", string="Child Clearance Type", readonly=False)
    selected_child_clearance_receipt_no = fields.Char(related="selected_child_clearance_id.clearance_receipt_no", string="Child Customs Clearance Receipt No.", readonly=False)
    selected_child_clearance_hs_code_qty = fields.Integer(related="selected_child_clearance_id.hs_code_qty", string="Child HS Code Qty", readonly=False)
    selected_child_clearance_extra_reason = fields.Selection(related="selected_child_clearance_id.extra_reason", string="Child Additional Reason", readonly=False)
    selected_child_clearance_extra_remark = fields.Char(related="selected_child_clearance_id.extra_remark", string="Child Additional Remark", readonly=False)
    selected_child_clearance_actual_datetime = fields.Datetime(related="selected_child_clearance_id.actual_datetime", string="Child Actual Date", readonly=False)
    selected_child_clearance_remark = fields.Text(related="selected_child_clearance_id.remark", string="Child Clearance Remark", readonly=False)
    selected_child_clearance_invoice_lines = fields.One2many(related="selected_child_clearance_id.invoice_line_ids", string="Child Clearance Vendor Invoice Lines", readonly=False)
    selected_child_clearance_charge_lines = fields.One2many(related="selected_child_clearance_id.charge_line_ids", string="Child Clearance Charge Lines", readonly=False)
    selected_child_clearance_container_line_ids = fields.Many2many(related="selected_child_clearance_id.clearance_container_ids", string="Child Clearance Containers", readonly=True)
    selected_child_clearance_is_overdue = fields.Boolean(related="selected_child_clearance_id.is_clearance_overdue", string="Is Child Clearance Overdue", readonly=True)
    selected_child_clearance_overdue_blocking_reason_id = fields.Many2one(related="selected_child_clearance_id.overdue_blocking_reason_id", string="Child Clearance Overdue Blocking Reason", readonly=False)
    selected_child_clearance_overdue_blocking_reason_short_name = fields.Char(related="selected_child_clearance_id.overdue_blocking_reason_short_name", string="Child Clearance Overdue Blocking Reason Short Name", readonly=True)
    selected_child_clearance_overdue_reason_note = fields.Text(related="selected_child_clearance_id.overdue_reason_note", string="Child Clearance Overdue Reason Note", readonly=False)
    selected_child_clearance_overdue_handle_result = fields.Selection(related="selected_child_clearance_id.overdue_handle_result", string="Child Clearance Overdue Handle Result", readonly=False)
    selected_child_clearance_overdue_result_note = fields.Text(related="selected_child_clearance_id.overdue_result_note", string="Child Clearance Overdue Result Note", readonly=False)

    @api.onchange("handover_overdue_blocking_reason_id", "clearance_overdue_blocking_reason_id", "selected_child_handover_overdue_blocking_reason_id", "selected_child_clearance_overdue_blocking_reason_id")
    def onchange_overdue_blocking_reason(self):
        for rec in self:
            rec.handover_overdue_blocking_reason_short_name = rec.handover_overdue_blocking_reason_id.short_name if rec.handover_overdue_blocking_reason_id else False
            rec.clearance_overdue_blocking_reason_short_name = rec.clearance_overdue_blocking_reason_id.short_name if rec.clearance_overdue_blocking_reason_id else False
            rec.selected_child_handover_overdue_blocking_reason_short_name = rec.selected_child_handover_overdue_blocking_reason_id.short_name if rec.selected_child_handover_overdue_blocking_reason_id else False
            rec.selected_child_clearance_overdue_blocking_reason_short_name = rec.selected_child_clearance_overdue_blocking_reason_id.short_name if rec.selected_child_clearance_overdue_blocking_reason_id else False

    @api.depends("handover_lines.parent_id", "handover_lines.state", "handover_lines.payable_state", "handover_lines.receivable_state", "clearance_lines.parent_id", "clearance_lines.state", "clearance_lines.payable_state", "clearance_lines.receivable_state")
    def _compute_operation_fee_states(self):
        for rec in self:
            handovers = rec.handover_lines.filtered(lambda line: not line.parent_id and line.state != "cancelled")
            clearances = rec.clearance_lines.filtered(lambda line: not line.parent_id and line.state != "cancelled")
            if not handovers:
                rec.handover_payable_state = "not_applicable"
                rec.handover_receivable_summary_state = "not_applicable"
            else:
                handover_payable_states = set(handovers.mapped("payable_state"))
                rec.handover_payable_state = "paid" if handover_payable_states == {"paid"} else "not_applied" if handover_payable_states == {"not_applied"} else "paying"
                rec.handover_receivable_summary_state = "confirmed" if not handovers.filtered(lambda line: line.receivable_state != "confirmed") else "draft"
            if not clearances:
                rec.clearance_payable_state = "not_applied"
                rec.clearance_receivable_summary_state = "draft"
            else:
                clearance_payable_states = set(clearances.mapped("payable_state"))
                rec.clearance_payable_state = "paid" if clearance_payable_states == {"paid"} else "not_applied" if clearance_payable_states == {"not_applied"} else "paying"
                rec.clearance_receivable_summary_state = "confirmed" if not clearances.filtered(lambda line: line.receivable_state != "confirmed") else "draft"
            rec.operation_fee_completed = bool(clearances) and not clearances.filtered(lambda line: line.payable_state != "paid" or line.receivable_state != "confirmed") and not handovers.filtered(lambda line: line.payable_state != "paid" or line.receivable_state != "confirmed")

    def write(self, vals):
        values = dict(vals)
        handover_field_map = {
            "handover_overdue_blocking_reason_id": "overdue_blocking_reason_id",
            "handover_overdue_reason_note": "overdue_reason_note",
            "handover_overdue_handle_result": "overdue_handle_result",
            "handover_overdue_result_note": "overdue_result_note",
        }
        clearance_field_map = {
            "clearance_overdue_blocking_reason_id": "overdue_blocking_reason_id",
            "clearance_overdue_reason_note": "overdue_reason_note",
            "clearance_overdue_handle_result": "overdue_handle_result",
            "clearance_overdue_result_note": "overdue_result_note",
        }
        child_handover_field_map = {
            "selected_child_handover_extra_reason": "extra_reason",
            "selected_child_handover_extra_remark": "extra_remark",
            "selected_child_handover_overdue_blocking_reason_id": "overdue_blocking_reason_id",
            "selected_child_handover_overdue_reason_note": "overdue_reason_note",
            "selected_child_handover_overdue_handle_result": "overdue_handle_result",
            "selected_child_handover_overdue_result_note": "overdue_result_note",
        }
        child_clearance_field_map = {
            "selected_child_clearance_extra_reason": "extra_reason",
            "selected_child_clearance_extra_remark": "extra_remark",
            "selected_child_clearance_overdue_blocking_reason_id": "overdue_blocking_reason_id",
            "selected_child_clearance_overdue_reason_note": "overdue_reason_note",
            "selected_child_clearance_overdue_handle_result": "overdue_handle_result",
            "selected_child_clearance_overdue_result_note": "overdue_result_note",
        }
        handover_vals = {target_name: values.pop(source_name) for source_name, target_name in handover_field_map.items() if source_name in values}
        clearance_vals = {target_name: values.pop(source_name) for source_name, target_name in clearance_field_map.items() if source_name in values}
        child_handover_vals = {target_name: values.pop(source_name) for source_name, target_name in child_handover_field_map.items() if source_name in values}
        child_clearance_vals = {target_name: values.pop(source_name) for source_name, target_name in child_clearance_field_map.items() if source_name in values}
        values.pop("handover_overdue_blocking_reason_short_name", None)
        values.pop("clearance_overdue_blocking_reason_short_name", None)
        values.pop("selected_child_handover_overdue_blocking_reason_short_name", None)
        values.pop("selected_child_clearance_overdue_blocking_reason_short_name", None)
        result = super().write(values)
        for rec in self:
            if handover_vals and rec.handover_id:
                rec.handover_id.write(handover_vals)
            if clearance_vals and rec.clearance_id:
                rec.clearance_id.write(clearance_vals)
            if child_handover_vals and rec.selected_child_handover_id:
                rec.selected_child_handover_id.write(child_handover_vals)
            if child_clearance_vals and rec.selected_child_clearance_id:
                rec.selected_child_clearance_id.write(child_clearance_vals)
        return result

    # 货到港码头信息
    port_id = fields.Many2one("world.depot.port.node", string="Port", tracking=True)
    terminal_id = fields.Many2one("world.depot.port.node", string="Terminal", tracking=True)
    arrival_confirm_user_id = fields.Many2one("res.users", string="Arrival Confirm User", tracking=True, copy=False,
                                              readonly=True, index=True)
    arrival_confirm_time = fields.Datetime(string="Arrival Confirm Time", tracking=True, copy=False, readonly=True)
    is_arrived = fields.Boolean(string="Is Arrived", compute="_compute_is_arrived", store=True)

    #逾期信息
    is_waybill_overdue = fields.Boolean(string="Is Waybill Overdue", compute="_compute_is_waybill_overdue")
    arrival_overdue_reason = fields.Selection([
        ("carrier_reason", "Carrier Reason"),
        ("internal_reason", "Internal Operation Reason"),
        ("other", "Other"),
    ], string="Arrival Overdue Block Reason", tracking=True, copy=False)
    arrival_overdue_reason_note = fields.Text(string="Arrival Overdue Reason Note", tracking=True)

    arrival_overdue_result = fields.Selection([
        ("contact_carrier", "Contacted Carrier And Confirmed New ETA/ATA"),
        ("backfill_ata", "Backfilled ATA"),
        ("assigned_followup", "Assigned Operator For Follow-up"),
        ("other", "Other"),
    ], string="Arrival Overdue Handle Result", tracking=True, copy=False)
    arrival_overdue_result_note = fields.Text(string="Arrival Overdue Result Note", tracking=True)

    @api.depends("ata")
    def _compute_is_arrived(self):
        for rec in self:
            rec.is_arrived = bool(rec.ata)

    @api.constrains(
        "arrival_overdue_reason", "arrival_overdue_reason_note",
        "arrival_overdue_result", "arrival_overdue_result_note"
    )
    def check_waybill_overdue_other_notes(self):
        for rec in self:
            if rec.arrival_overdue_reason == "other" and not (rec.arrival_overdue_reason_note or "").strip():
                raise ValidationError(_("Reason Note is required when Overdue Reason is Other."))
            if rec.arrival_overdue_result == "other" and not (rec.arrival_overdue_result_note or "").strip():
                raise ValidationError(_("Result Note is required when Overdue Result is Other."))

    @api.depends("eta", "ata")
    def _compute_is_waybill_overdue(self):
        for rec in self:
            if not rec.eta:
                rec.is_waybill_overdue = False
                continue
            today = fields.Date.context_today(rec)
            if rec.ata:
                rec.is_waybill_overdue = rec.ata > rec.eta
            else:
                rec.is_waybill_overdue = rec.eta < today



    def action_open_arrival_wizard(self):
        for rec in self:
            if rec.state != "confirm":
                raise ValidationError(_("Only waybills in confirm status can confirm cargo arrival"))
        return {
            "type": "ir.actions.act_window",
            "name": _("Cargo Arrival Confirmation"),
            "res_model": "waybill.arrival.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_waybill_id": self.id,
                "default_actual_arrival_date": fields.Date.context_today(self),
            }
        }

    # @api.constrains('other_docs_ids')
    # def constrain_required_documents(self):
    #     if self.env.context.get("skip_bl_required"):
    #         return
    #     for rec in self:
    #         bl_lines = rec.other_docs_ids.filtered(lambda l: l.bill_doc_type == 'bl' and l.file)
    #         if not bl_lines:
    #             raise ValidationError(_("BL file is required."))

    def name_get(self):
        res = []
        for rec in self:
            parts = []
            if rec.bl_number:
                parts.append(f"BL:{rec.bl_number}")
            if rec.hbl_number:
                parts.append(f"HBL:{rec.hbl_number}")
            res.append((rec.id, " / ".join(parts)))
        return res

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        args = args or []
        domain = args
        if name:
            domain = ["|",
                      ("bl_number", operator, name),
                      ("hbl_number", operator, name)
                      ] + args
        records = self.search(domain, limit=limit)
        return records.name_get()

    @api.depends("container_ids")
    def _compute_container_ids(self):
        for rec in self:
            rec.container_qty = len(rec.container_ids)

    def action_create_handover(self):
        for rec in self:
            if rec.state == "done":
                raise UserError(_("This waybill has been done. Formal order replacement operations cannot be created."))
            if rec.state != "confirm":
                raise UserError(_("Please change the status to confirm"))

            attachment_lines = [(0, 0, {
                "doc_type": ln.bill_doc_type,
                "remark": ln.description,
                "file": ln.file,
                "name": ln.filename,
            }) for ln in rec.other_docs_ids]

            charge_lines = [(0, 0, {
                "charge_item_id": ln.charge_item_id.id,
                "charge_origin_type": 'quotation',
                "unit_price": ln.unit_price,
                "is_fixed_fee": ln.is_fixed_fee,
            }) for ln in rec.quotation_id.quotation_thc_lines]

            handover_id = rec.env['operation.order.handover'].sudo().create({
                'waybill_id': rec.id,
                'project_id': rec.project.id,
                'shipping_line_id': rec.shipping.id,
                'container_qty': rec.container_qty,
                "attachment_line_ids": attachment_lines,
                "charge_line_ids": charge_lines,
            })
            rec.handover_id = handover_id.id
            return {
                "type": "ir.actions.act_window",
                "name": "Handover",
                "res_model": "operation.order.handover",
                "views": [(self.env.ref("wd_iffm.view_operation_order_handover_form").id, "form")],
                "view_mode": "form",
                "res_id": handover_id.id,
                "target": "current",
            }

    def action_create_handover_from_waybill_tab(self):
        for rec in self:
            if rec.handover_id:
                raise UserError(_("Handover already exists."))
            rec.action_create_handover()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_create_clearance(self):
        self.ensure_one()
        if self.state == "done":
            raise UserError(_("This waybill has been done. Formal order replacement operations cannot be created."))
        if self.state != "confirm":
            raise UserError(_("Please change the status to confirm"))
        if not self.container_ids:
            raise UserError(_("No container found on this waybill."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Select Containers"),
            "res_model": "waybill.create.clearance.wizard",
            "view_mode": "form",
            "views": [(self.env.ref("wd_iffm.view_waybill_create_clearance_wizard_form").id, "form")],
            "target": "new",
            "context": {
                "active_model": "world.depot.waybill",
                "active_id": self.id,
            },
        }

    def action_create_clearance_from_waybill_tab(self):
        for rec in self:
            if rec.clearance_id:
                raise UserError(_("Clearance already exists."))
            rec.action_create_clearance_all_create()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_create_child_handover_from_waybill_tab(self):
        for rec in self:
            if not rec.handover_id:
                raise UserError(_("Main handover is required before creating a child handover."))
            result = rec.handover_id.action_create_child_handover_workbench()
            rec.write({"selected_child_handover_id": result["child"]["id"]})
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_confirm_handover_receivable_from_waybill_tab(self):
        result = True
        for rec in self:
            if not rec.handover_id:
                raise UserError(_("Main handover is required before confirming receivable."))
            result = rec.handover_id.action_confirm_receivable()
        result["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return result

    def action_confirm_child_handover_receivable_from_waybill_tab(self):
        result = True
        for rec in self:
            if not rec.selected_child_handover_id:
                raise UserError(_("Please select a child handover first."))
            result = rec.selected_child_handover_id.action_confirm_receivable()
        result["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return result

    def action_unconfirm_handover_receivable_from_waybill_tab(self):
        result = True
        for rec in self:
            if not rec.handover_id:
                raise UserError(_("Main handover is required before unconfirming receivable."))
            result = rec.handover_id.action_unconfirm_receivable()
        result["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return result

    def action_unconfirm_child_handover_receivable_from_waybill_tab(self):
        result = True
        for rec in self:
            if not rec.selected_child_handover_id:
                raise UserError(_("Please select a child handover first."))
            result = rec.selected_child_handover_id.action_unconfirm_receivable()
        result["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return result

    def action_create_child_clearance_from_waybill_tab(self):
        for rec in self:
            if not rec.clearance_id:
                raise UserError(_("Main clearance is required before creating a child clearance."))
            result = rec.clearance_id.action_create_child_clearance_workbench()
            rec.write({"selected_child_clearance_id": result["child"]["id"]})
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_confirm_clearance_receivable_from_waybill_tab(self):
        result = True
        for rec in self:
            if not rec.clearance_id:
                raise UserError(_("Main clearance is required before confirming receivable."))
            result = rec.clearance_id.action_confirm_receivable()
        result["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return result

    def action_confirm_child_clearance_receivable_from_waybill_tab(self):
        result = True
        for rec in self:
            if not rec.selected_child_clearance_id:
                raise UserError(_("Please select a child clearance first."))
            result = rec.selected_child_clearance_id.action_confirm_receivable()
        result["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return result

    def action_unconfirm_clearance_receivable_from_waybill_tab(self):
        result = True
        for rec in self:
            if not rec.clearance_id:
                raise UserError(_("Main clearance is required before unconfirming receivable."))
            result = rec.clearance_id.action_unconfirm_receivable()
        result["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return result

    def action_unconfirm_child_clearance_receivable_from_waybill_tab(self):
        result = True
        for rec in self:
            if not rec.selected_child_clearance_id:
                raise UserError(_("Please select a child clearance first."))
            result = rec.selected_child_clearance_id.action_unconfirm_receivable()
        result["params"]["next"] = {"type": "ir.actions.client", "tag": "soft_reload"}
        return result

    def action_create_pickup_requirement(self):
        self.ensure_one()
        if not self.is_arrived:
            raise UserError(_("Only arrived waybill can create pickup requirement."))
        if not self.release_received and not self.custom_clearance:
            raise UserError(_("Please receive release and clearance first."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Pickup Requirement"),
            "res_model": "import.pickup.requirement",
            "view_mode": "form",
            "views": [(self.env.ref("wd_iffm.view_import_pickup_requirement_form").id, "form")],
            "target": "current",
            "context": {
                "default_waybill_id": self.id,
            },
        }

    def action_create_clearance_all_create(self):
        env_clearance = self.env["operation.order.clearance"]
        for rec in self:
            if rec.state != "confirm":
                raise UserError(_("Please change the status to confirm"))
            if not rec.container_ids:
                raise UserError(_("Please select at least one container."))

            main_clearance = env_clearance.sudo().search([
                ("waybill_id", "=", rec.id),
                ("parent_id", "=", False),
                ("state", "!=", "cancelled"),
            ], limit=1)
            if main_clearance:
                raise UserError(_("Main clearance already exists."))

            clearances = env_clearance.sudo().search([
                ("waybill_id", "=", rec.id),
                ("state", "!=", "cancelled"),
            ])
            used_ids = set(clearances.mapped("clearance_container_ids").ids)
            selected_ids = set(rec.container_ids.ids)
            duplicated_ids = selected_ids & used_ids
            if duplicated_ids:
                duplicated = self.env["world.depot.waybill.container"].sudo().browse(list(duplicated_ids))
                nums = ", ".join(duplicated.mapped("container_number"))
                raise UserError(_("These containers are already in clearance orders: %s") % nums)

            attachment_lines = [(0, 0, {
                "doc_type": ln.bill_doc_type,
                "remark": ln.description,
                "file": ln.file,
                "name": ln.filename,
            }) for ln in rec.other_docs_ids]

            charge_lines = [(0, 0, {
                "charge_item_id": ln.charge_item_id.id,
                "charge_origin_type": 'quotation',
                "unit_price": ln.unit_price,
                "is_fixed_fee": ln.is_fixed_fee,
            }) for ln in rec.quotation_id.quotation_customs_lines]

            clearance_id = env_clearance.create({
                'waybill_id': rec.id,
                'project_id': rec.project.id,
                'shipping_line_id': rec.shipping.id,
                'handover_id': rec.handover_id.id,
                'container_qty': len(rec.container_ids),
                'clearance_container_ids': [(6, 0, rec.container_ids.ids)],
                "attachment_line_ids": attachment_lines,
                "charge_line_ids": charge_lines,
            })
            rec.clearance_id = clearance_id.id
            return {
                "type": "ir.actions.act_window",
                "name": "Clearance",
                "res_model": "operation.order.clearance",
                "views": [(self.env.ref("wd_iffm.operation_order_clearance_form_view").id, "form")],
                "view_mode": "form",
                "res_id": clearance_id.id,
                "target": "current",
            }

    def save_record(self):
        """Custom save method to handle record saving."""
        for record in self:
            # Perform any additional logic here if needed
            record.write(record._convert_to_write(record.read()[0]))
        return True

    @api.model_create_multi
    def create(self, vals_list):
        sequence_date = fields.Date.today()
        sequence_env = self.env["ir.sequence"]

        for vals in vals_list:
            if not vals.get("billno"):
                vals["billno"] = sequence_env.next_by_code("seq.waybill", sequence_date=sequence_date) or _("New")
            if not vals.get("state"):
                vals["state"] = "new"

        return super().create(vals_list)

    def action_done_order(self):
        env_handover = self.env["operation.order.handover"]
        env_clearance = self.env["operation.order.clearance"]
        for rec in self:
            if rec.state != "confirm":
                raise UserError(_("Only confirmed waybill can be done."))
            if not rec.ata:
                raise UserError(_("ATA is required before Done."))
            clearance_records = env_clearance.sudo().search([("waybill_id", "=", rec.id), ("parent_id", "=", False), ("state", "!=", "cancelled")])
            if not clearance_records:
                raise UserError(_("At least one active clearance is required before Done."))
            if clearance_records.filtered(lambda line: line.receivable_state != "confirmed"):
                raise UserError(_("All active clearance receivables must be confirmed before Done."))
            if clearance_records.filtered(lambda line: not line.all_advance_paid):
                raise UserError(_("All active clearance vendor invoices must be paid before Done."))
            handover_records = env_handover.sudo().search([("waybill_id", "=", rec.id), ("parent_id", "=", False), ("state", "!=", "cancelled")])
            if handover_records.filtered(lambda line: line.receivable_state != "confirmed"):
                raise UserError(_("All active handover receivables must be confirmed before Done."))
            if handover_records.filtered(lambda line: not line.all_advance_paid):
                raise UserError(_("All active handover vendor invoices must be paid before Done."))
            rec.write({"state": "done"})
        return True

    def action_confirm_order(self):
        for rec in self:
            if rec.state != "new":
                raise UserError(_("Only new waybills can be confirmed."))
            if not rec.container_ids:
                raise UserError(_("Please create container first."))

            quotation = rec.project.quotation_id
            if not quotation:
                raise UserError(_("Please configure a quotation for the project."))
            if quotation.state != "active" or not quotation.is_active:
                raise UserError(_("The project quotation must be active."))

            pricing_date = rec.ata or rec.eta or fields.Date.context_today(rec)
            if quotation.effective_from > pricing_date:
                raise UserError(_("The quotation effective date is later than the pricing date."))
            if quotation.effective_to and quotation.effective_to < pricing_date:
                raise UserError(_("The quotation has expired on the pricing date."))

            rec.write({
                "state": "confirm",
                "quotation_id": quotation.id,
                "quotation_effective_date": pricing_date,
            })

        return True

    def action_unconfirm_order(self):
        env_handover = self.env["operation.order.handover"]
        env_clearance = self.env["operation.order.clearance"]

        # if not self.env.user.has_group("base.group_system"):
        #     raise UserError(_("Only administrators can unconfirm waybills."))

        for rec in self:
            if rec.state != "confirm":
                raise UserError(_("Only confirmed waybills can be unconfirmed."))

            handover_count = env_handover.sudo().search_count([
                ("waybill_id", "=", rec.id),
                ("state", "!=", "cancelled"),
            ])
            clearance_count = env_clearance.sudo().search_count([
                ("waybill_id", "=", rec.id),
                ("state", "!=", "cancelled"),
            ])
            if handover_count or clearance_count:
                raise UserError(
                    _("Waybills with active handover or clearance orders cannot be unconfirmed.")
                )

            rec.write({
                "state": "new",
                "quotation_id": False,
                "quotation_effective_date": False,
            })

        return True

    def action_cancel_order(self):
        env_handover = self.env["operation.order.handover"]
        env_clearance = self.env["operation.order.clearance"]

        # if not self.env.user.has_group("base.group_system"):
        #     raise UserError(_("Only administrators can cancel waybills."))

        for rec in self:
            if rec.state != "new":
                raise UserError(_("Only new waybills can be cancelled."))
            handover_count = env_handover.sudo().search_count([
                ("waybill_id", "=", rec.id),
                ("state", "!=", "cancelled"),
            ])
            clearance_count = env_clearance.sudo().search_count([
                ("waybill_id", "=", rec.id),
                ("state", "!=", "cancelled"),
            ])
            if handover_count or clearance_count:
                raise UserError(
                    _("Waybills with active handover or clearance orders cannot be cancelled.")
                )

            rec.write({
                "state": "cancel",
            })

        return True

        # check waybillno unique

    @api.constrains('bl_number')
    def _check_bl_number_id(self):
        for r in self:
            if r.bl_number:
                domain = [
                    ('bl_number', '=', r.bl_number),
                    ('state', '!=', 'cancel'),
                    ('id', '!=', r.id),
                ]
                existing_records = self.search(domain)
                if existing_records:
                    raise UserError(_('Bill of Lading must be unique per Waybill'))

    @api.constrains('bl_number', 'hbl_number')
    def _check_bl_hbl_number_id(self):
        for r in self:
            if not r.bl_number and not r.hbl_number:
                raise UserError(_('Either Bill of Lading or House Bill of Lading must be provided.'))


# 其他附件
class WaybillOtherDocs(models.Model):
    _name = 'world.depot.waybill.other.docs'
    _description = 'world.depot.waybill.other.docs'

    description = fields.Text(string='Description')
    file = fields.Binary(string='File')
    filename = fields.Char(string='File name')
    waybill_id = fields.Many2one('world.depot.waybill', string='Waybill BillNo', ondelete='cascade')
    bill_doc_type = fields.Selection([("bl", "BL"), ("other", "Other")], string="Document Type",
                                required=True, index=True, default="bl")


    @api.constrains('file', 'bill_doc_type', 'waybill_id')
    def constrain_waybill_bl_required(self):
        for rec in self:
            if not rec.waybill_id:
                continue
            waybill = rec.waybill_id
            bl_count = len(waybill.other_docs_ids.filtered(lambda l: l.bill_doc_type == 'bl' and l.file))
            if bl_count == 0:
                raise ValidationError(_("BL file is required."))

# 集装箱号
class WaybillContainer(models.Model):
    _name = 'world.depot.waybill.container'
    _description = 'world.depot.waybill.container'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    container_number = fields.Char(string='Container Number', required=True)
    container_type = fields.Selection(
        selection=[
            ('20GP', '20GP'),
            ('40GP', '40GP'),
            ('40HQ', '40HQ'),
            ('40HC', '40HC'),
            ('45HQ', '45HQ'),
            ('OT', 'OT'),
            ('FR', 'FR'),
            ('RF', 'RF'),
        ],
        string='Container Type',

    )
    weight = fields.Float(string='Weight (kg)')




    seal_number = fields.Char(string='Seal Number')

    volume = fields.Float(string='Volume (m³)', default=0.0)
    pallets = fields.Float(string='Pallets', default=0)
    quantity = fields.Float(string='Packages', default=1)

    mode = fields.Char(string='Model', help='Container mode, e.g., CY/CY, etc.')
    temperature = fields.Char(string='Temperature', help='Temperature control for refrigerated containers')
    humidity = fields.Char(string='Humidity', help='Humidity control for refrigerated containers')

    remark = fields.Text(string='Remark', tracking=True)

    # (港到仓)运输信息
    loading_reference = fields.Char(string='Loading Reference', tracking=True)
    loading_date = fields.Date(string='Loading Date', tracking=True)
    unloading_date = fields.Date(string='Unloading Date', tracking=True)
    unloading_location = fields.Many2one('res.partner', string='Unloading Location', )
    drop_off_date = fields.Date(string='Drop Off Date', tracking=True)
    drop_off_location = fields.Many2one('res.partner', string='Dropoff Location', )

    # 关联运单
    waybill_id = fields.Many2one('world.depot.waybill', string='Waybill BillNo',ondelete='set null')
    bl_number = fields.Char(string='Bill Number',related='waybill_id.bl_number',store=True)

    # 关联运单箱单
    packing_list_ids = fields.One2many('world.depot.waybill.packing.list', 'container_id', string='Packing Lists',
                                       help='Packing lists associated with this container')


# 箱单
class WaybillPackingList(models.Model):
    _name = 'world.depot.waybill.packing.list'
    _description = 'world.depot.waybill.packing.list'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    container_number = fields.Char(string='Container Number')
    product_id = fields.Many2one('product.product', string='Product')
    adr = fields.Boolean(string='ADR', help='Indicates if the product is classified as ADR (dangerous goods)')
    un_number = fields.Char(string='UN Number', help='United Nations number for dangerous goods classification')
    pallets = fields.Float(string='Pallets', default=0)
    quantity = fields.Float(string='Quantity', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure',
                             default=lambda self: self.env.ref('uom.product_uom_unit', raise_if_not_found=False))
    description = fields.Text(string='Description')
    total_weight = fields.Float(string='Total Weight (kg)', default=0.0)
    total_volume = fields.Float(string='Total Volume (m³)', default=0.0)
    total_packages = fields.Integer(string='Total Packages', default=0)

    remark = fields.Text(string='Remark', tracking=True)

    # 关联运单
    waybill_id = fields.Many2one('world.depot.waybill', string='Waybill BillNo', ondelete='cascade')
    # 关联集装箱
    container_id = fields.Many2one('world.depot.waybill.container', string='Container', ondelete='cascade')

    @api.constrains('adr')
    def _check_adr(self):
        for record in self:
            if record.adr and not record.un_number:
                raise ValidationError(_("UN Number must be provided when ADR is selected."))

    @api.model
    def _cron_related_container(self):
        for rec in self:
            if not rec.container_id and rec.container_number:
                container_number = rec.container_number
                waybill_id = rec.waybill_id
                container = self.env['world.depot.waybill.container'].search([
                    ('container_number', '=', container_number),
                    ('waybill_id', '=', waybill_id)
                ],
                    limit=1)
                if container:
                    rec.container_id = container.id
                else:
                    raise ValidationError(_("Container with number %s not found.") % container_number)
            if rec.container_id:
                rec.waybill_id = rec.container_id.waybill_id
                rec.container_number = rec.container_id.container_number
