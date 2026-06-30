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
    _rec_name = 'billno'
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
    quotation_id = fields.Many2one("charge.quotation", related='project.quotation_id', store=True, string="Quotation",
                                   index=True, tracking=True)
    container_qty = fields.Integer(string="Container Qty",compute="_compute_container_ids", tracking=True)

    handover_id = fields.Many2one("operation.order.handover", string="Handover")
    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance")

    # 货到港码头信息
    port_id = fields.Many2one("world.depot.port.node", string="Port", tracking=True)
    terminal_id = fields.Many2one("world.depot.port.node", string="Terminal", tracking=True)
    arrival_confirm_user_id = fields.Many2one("res.users", string="Arrival Confirm User", tracking=True, copy=False,
                                              readonly=True, index=True)
    arrival_confirm_time = fields.Datetime(string="Arrival Confirm Time", tracking=True, copy=False, readonly=True)
    is_arrived = fields.Boolean(string="Is Arrived")

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

    def action_done_order(self):
        for rec in self:
            if rec.state != "confirm":
                raise UserError(_("Only confirmed waybill can be done."))
            if not rec.release_received or not rec.custom_clearance:
                raise UserError(_("Release Received and Custom Clearance must both be completed before Done."))
            rec.write({"state": "done"})
        return True

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

    @api.constrains('other_docs_ids')
    def constrain_required_documents(self):
        if self.env.context.get("skip_bl_required"):
            return
        for rec in self:
            bl_lines = rec.other_docs_ids.filtered(lambda l: l.bill_doc_type == 'bl' and l.file)
            if not bl_lines:
                raise ValidationError(_("BL file is required."))

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

    def action_create_clearance_create_clearance(self):
        for rec in self:
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
            }) for ln in rec.quotation_id.quotation_customs_lines]

            clearance_id = rec.env['operation.order.clearance'].sudo().create({
                'waybill_id': rec.id,
                'project_id': rec.project.id,
                'shipping_line_id': rec.shipping.id,
                'handover_id': rec.handover_id.id,
                'container_qty': rec.container_qty,
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

    def action_confirm_order(self):
        for rec in self:
            if rec.state != 'new':
                raise UserError(_("You only can confirm New Order"))
            else:
                if not rec.project.quotation_id:
                    raise UserError(_("Please create quotation first"))
                rec.state = 'confirm'
                return True

    def action_unconfirm_order(self):
        for rec in self:
            if rec.state != 'confirm':
                raise UserError(_("You only can unconfirm Confirmed Order"))
            # elif not rec.container_ids:
            #     raise UserError(_("Please create container first"))
            else:
                rec.state = 'new'
                return True

    def action_cancel_order(self):
        for rec in self:
            if rec.state != 'new':
                raise UserError(_("You only can cancel New Order"))
            else:
                rec.state = 'cancel'
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
        required=True,
    )
    weight = fields.Float(string='Weight (kg)', required=True)




    seal_number = fields.Char(string='Seal Number')

    volume = fields.Float(string='Volume (m³)', default=0.0)
    pallets = fields.Float(string='Pallets', default=0)
    quantity = fields.Float(string='Packages', default=0)

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
    waybill_id = fields.Many2one('world.depot.waybill', string='Waybill BillNo', required=True, ondelete='cascade')

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
