import time
from datetime import datetime, timedelta
import requests
import logging
from odoo import _, models, fields, api
from odoo.exceptions import UserError
from collections import defaultdict
from odoo.exceptions import ValidationError


class Waybill(models.Model):
    _name = "world.depot.waybill"
    _description = "Waybill"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = 'billno'
    _order = "billno"

    billno = fields.Char(string='BillNo', readonly=True)
    project = fields.Many2one('project.project', string='Project', required=True, ondelete='cascade', )

    # ========== 基础信息 ==========
    bl_number = fields.Char(string='Bill of Lading')  # NKGA84065
    hbl_number = fields.Char(string='House Bill of Lading')  # HBL123456789
    document_number = fields.Char(string='Document No')  # S2502461054/C2501146242
    reference_number = fields.Char(string='Reference No')  # SHPR REF: AB20250404336

    # ========== 参与方信息 ==========
    shipping = fields.Many2one('res.partner', string='Shipping Line',
                               tracking=True)
    shipper = fields.Many2one('res.partner', string='Shipper/Exporter',
                              tracking=True)
    consignee = fields.Many2one('res.partner', string='Consignee/Importer',
                                tracking=True)
    notify_party = fields.Many2one('res.partner', string='Notify',
                                   tracking=True)

    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('confirm', 'Confirm'),
            ('cancel', 'Cancel'),
        ],
        default='new',
        string="State",
        tracking=True
    )
    remark = fields.Text(string='Remark', tracking=True)

    eta = fields.Date(string='ETA', tracking=True)
    ata = fields.Date(string='ATA', tracking=True)
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

    def save_record(self):
        """Custom save method to handle record saving."""
        for record in self:
            # Perform any additional logic here if needed
            record.write(record._convert_to_write(record.read()[0]))
        return True

    @api.model
    def create(self, values):
        """
        生成跟踪单号
        """
        times = fields.Date.today()

        values['billno'] = self.env['ir.sequence'].next_by_code('seq.waybill', times)
        values['state'] = 'new'
        return super(Waybill, self).create(values)

    def action_confirm_order(self):
        for rec in self:
            if rec.state != 'new':
                raise UserError(_("You only can confirm New Order"))
            else:
                rec.state = 'confirm'
                return True

    def action_unconfirm_order(self):
        for rec in self:
            if rec.state != 'confirm':
                raise UserError(_("You only can unconfirm Confirmed Order"))
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
    seal_number = fields.Char(string='Seal Number')
    weight = fields.Float(string='Weight (kg)', default=0.0)
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
