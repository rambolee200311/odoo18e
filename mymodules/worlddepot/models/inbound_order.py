import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta

_logger = logging.getLogger(__name__)


class InboundOrder(models.Model):
    _name = 'world.depot.inbound.order'
    _description = 'Inbound Order'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = 'billno'

    # Fields
    type = fields.Selection(
        selection=[
            ('inbound', 'Inbound'),
            ('service', 'Service'),
            ('transfer', 'Transfer'),
        ],
        default='inbound',
        string="Order Type",
        required=True,
        tracking=True
    )
    billno = fields.Char(string='Bill No', readonly=True, tracking=True)
    date = fields.Date(string='Order Date', required=True, tracking=True, default=fields.Date.today,
                       help='Planned date')
    a_date = fields.Date(string='Arrival Date', tracking=True, help='Planned date for inbound operation')
    i_date = fields.Date(string='Inbound Date', tracking=True, readonly=True, help='Real date for inbound operation')
    i_datetime = fields.Datetime(string='Inbound Date', tracking=True, readonly=True)
    project = fields.Many2one('project.project', string='Project', required=True)
    project_category_id = fields.Many2one(
        related='project.category',
        string='Project Category',
        store=True,
        readonly=True
    )
    pick_type = fields.Many2one('stock.picking.type', string='Picking Type', tracking=True,
                                domain=[('code', '=', 'incoming')])
    owner = fields.Many2one('res.partner', string='Owner', related='project.owner', tracking=True)
    # terminal = fields.Many2one('res.partner', string='Terminal', tracking=True)
    # from_partner = fields.Many2one('res.partner', string='From', tracking=True)
    # other_warehouse = fields.Many2one('res.partner', string='Other Warehouse', tracking=True)
    warehouse = fields.Many2one('stock.warehouse', string='Warehouse', tracking=True,
                                stored=True)
    remark = fields.Text(string='Remark')
    remark1 = fields.Text(string='Remark 1')
    reference = fields.Char(string='Reference', help='Reference for the Order No of Owner', required=True)
    bl_no = fields.Char(string='Bill of Lading')
    invoice_no = fields.Char(string='Invoice No')
    cntr_no = fields.Char(string='Container No')
    pallets = fields.Float(string='Pallets', readonly=True, default=0.0, tracking=True)
    scanning_quantity = fields.Float(string='Scanning Quantity', default=0.0, tracking=True)
    is_adr = fields.Boolean(string='ADR', default=True, tracking=True)

    weight_total = fields.Float(string='Total Weight (kg)', help='Total weight of the product in kilograms',
                                default=0.0, compute='_onchange_sum', store=True, tracking=True, )
    weight_total_input = fields.Float(
        string='Total Weight Input (kg)', help='Total weight of the product in kilograms', default=0.0, tracking=True
    )
    confirm_user_id = fields.Many2one(
        'res.users', string='Confirmed By', readonly=True, help="User who confirmed the order."
        , tracking=True)
    confirm_time_user_tz = fields.Datetime(
        string='Confirm Time (User Timezone)', readonly=True, help="Confirmation time in the user's timezone."
        , tracking=True)
    confirm_time_server = fields.Datetime(
        string='Confirm Time (Server)', readonly=True, help="Confirmation time in the server's timezone."
        , tracking=True)

    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('confirm', 'Confirmed'),
            ('cancel', 'Cancelled')
        ],
        default='new',
        string="State",
        tracking=True
    )
    status = fields.Selection(
        selection=[
            ('planning', 'Planning'),
            ('arrive', 'Arrived'),
            ('inbound', 'Inbound'),
        ],
        default='planning',
        string="Status",
        readonly=True,
        tracking=True
    )
    is_scan_sn = fields.Boolean(string='Scan Serial Number one by one', default=True, tracking=True)

    inbound_order_product_ids = fields.One2many(
        comodel_name='world.depot.inbound.order.product',
        inverse_name='inbound_order_id',
        string='Pallets of Inbound Order'
    )
    stock_picking_id = fields.Many2one(
        'stock.picking', string='Stock Picking', readonly=True,
        help='Reference to the related Stock Picking'
    )

    # Charges
    # 港至仓
    inbound_trucking_charge = fields.Float(
        string='Trucking Charge',
        default=0.0,
        tracking=True
    )

    # 港口其他费用
    inbound_terminal_surcharge = fields.Float(
        string='Terminal Surcharge',
        default=0.0,
        tracking=True
    )
    inbound_terminal_surcharge_remark = fields.Text(
        string='Terminal Surcharge Remark'
    )

    # 入库操作
    inbound_handling_charge = fields.Float(
        string='Inbound Handling',
        default=0.0,
        tracking=True
    )

    # 系统
    inbound_system_file_charge = fields.Float(
        string='System File and Document Admin Fee',
        default=10.0,
        tracking=True
    )

    # 危险品
    inbound_DGD_charge = fields.Float(
        string='Dangerous Goods Declaration Charge',
        default=7.5,
        tracking=True
    )
    # 扫描费用
    inbound_scanning_charge = fields.Float(string='Scanning Charge', default=0.0, tracking=True)

    inbound_order_doc_ids = fields.One2many('world.depot.inbound.order.docs',
                                            'inbound_order_id',
                                            string='Inbound Order Documents')

    inbound_order_charge_ids = fields.One2many('world.depot.inbound.order.charge',
                                               'inbound_order_id',
                                               string='Inbound Order Charges')
    # to cancel orders whose project is archived
    def cron_cancel_orders_with_archived_projects(self):
        """Scheduled action to cancel all orders whose project is archived."""
        # 查找所有项目已归档的订单
        orders_to_cancel = self.search([
            ('state', 'not in', ['cancel']),  # 排除已经取消的订单
            ('project.active', '=', False)  # 项目已归档（active=False）
        ])

        if orders_to_cancel:
            _logger.info("Found %d orders with archived projects to cancel", len(orders_to_cancel))

            for order in orders_to_cancel:
                try:
                    # 检查是否有相关的库存调拨单
                    if order.stock_picking_id and order.stock_picking_id.state == 'done':
                        _logger.warning("Cannot cancel order %s (ID: %s) because it has completed stock picking",
                                        order.billno, order.id)
                        continue

                    # 如果有未完成的库存调拨单，先删除
                    if order.stock_picking_id and order.stock_picking_id.state != 'done':
                        try:
                            order.stock_picking_id.action_cancel()
                            order.stock_picking_id.unlink()
                        except Exception as e:
                            _logger.error("Failed to delete stock picking for order %s: %s", order.billno, str(e))
                            continue

                    # 取消订单
                    order.state = 'cancel'
                    _logger.info("Successfully cancelled order %s with archived project", order.billno)

                except Exception as e:
                    _logger.error("Failed to cancel order %s: %s", order.billno, str(e))
                    continue

            _logger.info("Cancelled %d orders with archived projects", len(orders_to_cancel))
        else:
            _logger.info("No orders with archived projects found to cancel")

        return True

    # unlink inbound orders whose state is cancel
    def cron_unlink_inbound_orders_canceled(self):
        """
        Scheduled action to unlink inbound orders including their pallets, products, charges, and docs.
        Only unlink orders that are in 'new' or 'cancel' state and meet certain criteria.
        """
        # 定义删除条件：状态为 new 或 cancel 的订单
        domain = [
            ('state', 'in', ['new', 'cancel'])
        ]

        orders_to_delete = self.search(domain)

        if not orders_to_delete:
            _logger.info("No inbound orders found for deletion based on the criteria.")
            return True

        _logger.info("Found %d inbound orders to delete", len(orders_to_delete))

        deleted_count = 0
        error_count = 0

        for order in orders_to_delete:
            try:
                # 记录订单信息用于日志
                order_info = f"Order {order.billno or 'No BillNo'} (ID: {order.id})"

                # 检查是否有相关的库存调拨单，如果有则跳过（安全考虑）
                if order.stock_picking_id and order.stock_picking_id.state != 'cancel':
                    _logger.warning("Skipping %s: has active stock picking %s",
                                    order_info, order.stock_picking_id.name)
                    continue

                # 递归删除所有关联的one2many记录
                self._recursive_unlink_related_records(order)

                # 删除订单本身
                order.unlink()

                deleted_count += 1
                _logger.info("Successfully deleted %s", order_info)

            except Exception as e:
                error_count += 1
                _logger.error("Failed to delete order %s: %s", order_info, str(e))
                continue

        _logger.info("Cron completed: %d orders deleted, %d errors", deleted_count, error_count)
        return True

    def _recursive_unlink_related_records(self, record):
        """
        Recursively unlink all one2many records associated with the given record.
        """
        try:
            # 定义需要处理的关联模型字段
            related_fields = [
                'inbound_order_product_ids',  # 托盘产品
                'inbound_order_doc_ids',  # 文档
                'inbound_order_charge_ids',  # 费用
            ]

            for field_name in related_fields:
                if hasattr(record, field_name):
                    related_records = record[field_name]
                    if related_records:
                        _logger.debug("Deleting %d records from %s for order %s",
                                      len(related_records), field_name, record.billno)

                        # 对于产品记录，需要递归删除其关联的托盘和序列号
                        if field_name == 'inbound_order_product_ids':
                            for product_record in related_records:
                                self._recursive_unlink_product_related(product_record)

                        # 删除关联记录
                        related_records.unlink()

        except Exception as e:
            _logger.error("Error unlinking related records for order %s: %s", record.billno, str(e))
            raise

    def _recursive_unlink_product_related(self, product_record):
        """
        Recursively unlink all records related to a product record.
        """
        try:
            # 删除托盘产品关联
            if hasattr(product_record, 'inbound_order_product_pallet_ids'):
                pallets = product_record.inbound_order_product_pallet_ids
                if pallets:
                    _logger.debug("Deleting %d pallet records for product %s",
                                  len(pallets), product_record.id)
                    pallets.unlink()

            # 删除序列号关联
            if hasattr(product_record, 'product_serial_number_ids'):
                serial_numbers = product_record.product_serial_number_ids
                if serial_numbers:
                    _logger.debug("Deleting %d serial number records for product %s",
                                  len(serial_numbers), product_record.id)
                    serial_numbers.unlink()

        except Exception as e:
            _logger.error("Error unlinking product related records for product %s: %s",
                          product_record.id, str(e))
            raise

    # Compute adr dgd charge
    @api.depends('is_adr')
    def _compute_is_adr(self):
        for record in self:
            record.inbound_DGD_charge = 0.0
        """Compute if the order is ADR (Accord européen relatif au transport international des marchandises Dangereuses par Route).
        for record in self:
            if record.is_adr:
                record.inbound_DGD_charge = record.project.inbound_DGD_charge
            else:
                record.inbound_DGD_charge = 0.0
        """

    @api.depends('project')
    def _compute_charges(self):
        for record in self:
            if record.project:
                # record.warehouse = record.project.warehouse
                record.inbound_trucking_charge = 0.0
                if record.type == 'inbound':
                    record.inbound_trucking_charge = record.project.inbound_trucking_charge
            else:
                record.inbound_trucking_charge = 0.0

    # Methods
    @api.model
    def create(self, values):
        """Generate bill number and create record."""
        values['billno'] = self.env['ir.sequence'].next_by_code('seq.inbound.order')
        return super(InboundOrder, self).create(values)

    def save_record(self):
        """Custom save method to handle record saving."""
        for record in self:
            # Perform any additional logic here if needed
            for product in record.inbound_order_product_ids:
                # Ensure product is linked to the order
                product.inbound_order_id = record.id
                product._compute_product_description()
                product._compute_quantity()
            record.write(record._convert_to_write(record.read()[0]))
        return True

    def action_confirm(self):
        """Confirm the order."""
        for record in self:
            # Ensure owner and project are filled
            if not record.owner:
                raise UserError(_("Owner is required to confirm the order."))
            if not record.project:
                raise UserError(_("Project is required to confirm the order."))
            # Ensure Container No are filled
            if not record.cntr_no:
                raise UserError(_("Container No is required to confirm the order."))
            if record.type == 'inbound':
                # Ensure arrival date  is filled
                if not record.a_date:
                    raise UserError(_("Arrival Date is required to confirm the inbound order."))
                # Ensure at least one product line exists
                if not record.inbound_order_product_ids:
                    raise UserError(_("At least one pallet is required to confirm the order."))
                for pallet in record.inbound_order_product_ids:
                    if not pallet.inbound_order_product_pallet_ids or len(
                            pallet.inbound_order_product_pallet_ids) == 0:
                        raise UserError(_("At least one product is required for each pallet to confirm the order."))
                '''
                for product in record.inbound_order_product_ids:
                    # Ensure quantity and pallets are greater than zero and quantity is divisible by pallets
                    if product.quantity == 0 or not product.quantity:
                        raise UserError(
                            _("The quantity of product '%s' must be greater than zero to confirm the order.") % product.product_id.name
                        )
                    if product.pallets == 0 or not product.pallets:
                        raise UserError(
                            _("The pallets of product '%s' must be greater than zero to confirm the order.") % product.product_id.name
                        )
                    if product.quantity % product.pallets != 0:
                        raise UserError(
                            _("The quantity of product '%s' cannot be evenly divided by the number of pallets.") % product.product_id.name
                        )
                # check if serial number's quantity is equal to product's quantity
                for product in record.inbound_order_product_ids:
                    if product.is_serial_tracked:
                        if product.product_serial_number_ids:
                            total_quantity = sum(sn.quantity for sn in product.product_serial_number_ids)
                            if total_quantity != product.quantity:
                                raise UserError(
                                    _("The total quantity of serial numbers for product '%s' must match the product quantity.") % product.product_id.name
                                )        
                '''

            if record.state != 'new':
                raise UserError(_("Only new orders can be confirmed."))

            record.state = 'confirm'
            # Record the user who confirmed
            record.confirm_user_id = self.env.user
            # Record the confirmation time in the user's timezone
            user_time = fields.Datetime.context_timestamp(self, fields.Datetime.now())
            record.confirm_time_user_tz = fields.Datetime.to_string(user_time)
            # Record the server confirmation time
            record.confirm_time_server = fields.Datetime.now()

            # Automatically add followers
            try:
                inventory_admin_group = self.env.ref('stock.group_stock_manager')
                inventory_user_group = self.env.ref('stock.group_stock_user')
                valid_users = (inventory_admin_group.users | inventory_user_group.users).filtered('active')
                partner_ids = valid_users.partner_id.ids
                record.message_subscribe(partner_ids=partner_ids)
                record.message_post(
                    body=Markup(
                        "Inbound Order <a href='#' data-oe-model='world.depot.inbound.order' data-oe-id='%d'>%s</a> has been confirmed, please check it."
                    ) % (record.id, record.billno),
                    partner_ids=partner_ids,
                    subtype_id=self.env.ref('mail.mt_comment').id,  # Ensures HTML rendering
                    message_type='comment',  # Explicitly set the message type
                    notify=False  # Disable email notifications
                )

            except Exception as e:
                _logger.error("入库单关注者通知失败: %s | 单据: %s", str(e), record.billno)
                # 可选：raise UserError(_("通知发送失败，请手动检查"))  # 关键业务场景可中断

    def action_cancel(self):
        """Cancel the order."""
        for record in self:
            if record.state == 'cancel':
                raise UserError(_("This order %s has already been canceled.") % record.reference)

            if record.state == 'confirm':
                if record.stock_picking_id:
                    if record.stock_picking_id.state == 'done':
                        raise UserError(
                            _("Cannot cancel the order %s with an active stock picking that is done.") % record.reference)
                    # If the stock picking is not done, delete it
                    try:
                        record.stock_picking_id.unlink()
                    except Exception as e:
                        raise UserError(
                            _("Failed to delete stock picking for order %s: %s") % (record.reference, str(e)))

            record.state = 'cancel'

    def action_unconfirm(self):
        """Unconfirm the order."""
        for record in self:
            if record.state != 'confirm':
                raise UserError(_("Only confirmed orders can be unconfirmed."))
            related_picking = self.env['stock.picking'].search(
                [('inbound_order_id', '=', record.id), ('state', '!=', 'cancel')], limit=1
            )
            if related_picking:
                raise UserError(_("Cannot unconfirm an order with completed stock picking."))

            # Delete related receipts and stock moves not in "done" state
            related_receipts = self.env['stock.picking'].search([
                ('inbound_order_id', '=', record.id),
                ('state', '!=', 'done')
            ])
            for receipt in related_receipts:
                self.env['stock.move'].search([('picking_id', '=', receipt.id)]).unlink()
            related_receipts.unlink()

            record.state = 'new'
            record.confirm_user_id = False
            record.confirm_time_user_tz = False
            record.confirm_time_server = False

    '''
    def action_create_stock_picking_old(self):
        """Create the related stock picking with packages and move lines."""
        for record in self:
            # Ensure the order is confirmed
            if record.state != 'confirm':
                raise UserError(_("Stock picking can only be created from confirmed orders."))
            if not self.reference:
                raise UserError(_("Reference must be set before creating a stock picking."))
            if not record.pick_type:
                raise UserError(_("Picking Type is required to create a stock picking."))

            if not record.cntr_no:
                raise UserError(_("Container No is required to create packages."))

            if record.stock_picking_id:
                raise UserError(_("Stock picking already exists for this order."))

            # Check if stock picking already exists

            existing_picking = self.env['stock.picking'].search(
                [('inbound_order_id', '=', record.id),
                 ('state', '!=', 'cancel')],
                limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Inbound Order."))

            picking = self.env['stock.picking'].create({
                'picking_type_id': record.pick_type.id,
                'location_id': record.pick_type.default_location_src_id.id,
                'location_dest_id': record.pick_type.default_location_dest_id.id,
                'origin': record.billno,
                'partner_id': record.owner.id,
                'inbound_order_id': record.id,
                'owner_id': record.owner.id,
                'bill_of_lading': record.bl_no,
                'cntrno': record.cntr_no,
                'ref_1': record.reference,
                'planning_date': record.a_date,
                'inbound_order_id': record.id,
            })
            pallet_index = 1

            # Create packages and stock move lines
            for product in record.inbound_order_product_ids:
                if product.pallets <= 0 or product.quantity <= 0:
                    raise UserError(_("Invalid pallets or quantity for product '%s'.") % product.product_id.name)

                # Calculate the quantity per package
                quantity_per_package = product.quantity / product.pallets
                if not quantity_per_package.is_integer():
                    raise UserError(
                        _("Quantity must be evenly divisible by pallets for product '%s'.") % product.product_id.name)
                stock_move = self.env['stock.move'].create({
                    'name': product.product_id.name,
                    'product_id': product.product_id.id,
                    'product_uom_qty': product.quantity,
                    'product_uom': product.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                })

                quantity_per_package = int(quantity_per_package)

                for p_index in range(1, int(product.pallets) + 1):
                    package_name = f"{record.reference}-{record.cntr_no}-{str(pallet_index).zfill(4)}"

                    package = self.env['stock.quant.package'].search([('name', '=', package_name)])
                    if not package:
                        self.env['stock.quant.package'].create({
                            'name': package_name,
                            'package_use': 'disposable',
                        })
                    package = self.env['stock.quant.package'].search([('name', '=', package_name)])
                    pallet_index += 1
                    if product.product_id.tracking == 'serial' and record.is_scan_sn:
                        # Create `quantity_per_package` lines for serial-tracked products
                        for unit_index in range(1, quantity_per_package + 1):
                            self.env['stock.move.line'].create({
                                'move_id': stock_move.id,
                                'picking_id': picking.id,
                                'product_id': product.product_id.id,
                                'product_uom_id': product.product_id.uom_id.id,
                                'quantity': 1.00,  # Planned quantity
                                'location_id': picking.location_id.id,
                                'location_dest_id': picking.location_dest_id.id,
                                'result_package_id': package.id,
                            })
                    else:
                        # Create a single line for non-serial-tracked products
                        self.env['stock.move.line'].create({
                            'move_id': stock_move.id,
                            'picking_id': picking.id,
                            'product_id': product.product_id.id,
                            'product_uom_id': product.product_id.uom_id.id,
                            'quantity': quantity_per_package,  # Planned quantity
                            'location_id': picking.location_id.id,
                            'location_dest_id': picking.location_dest_id.id,
                            'result_package_id': package.id,
                        })

            record.stock_picking_id = picking.id

        # Return a success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Stock Picking Created'),
                'message': _('Stock picking with packages has been created successfully.'),
                'sticky': False,
            }
        }
        
    '''

    def unlink(self):
        for record in self:
            # Check state
            if record.state not in ['new', 'cancel']:
                raise UserError(_("Only new or cancelled orders can be deleted."))

            # Iterate through all fields of the model
            for field_name, field in record._fields.items():
                if field.type == 'one2many':
                    # Get the one2many records
                    one2many_records = record[field_name]
                    if one2many_records:
                        # Recursively unlink nested one2many records
                        for nested_record in one2many_records:
                            for nested_field_name, nested_field in nested_record._fields.items():
                                if nested_field.type == 'one2many':
                                    nested_one2many_records = nested_record[nested_field_name]
                                    if nested_one2many_records:
                                        nested_one2many_records.unlink()
                        one2many_records.unlink()

        return super(InboundOrder, self).unlink()

    def action_create_stock_picking(self):
        """Create the related stock picking with packages and move lines."""
        for record in self:
            # Ensure the order is confirmed
            if record.state != 'confirm':
                raise UserError(_("Stock picking can only be created from confirmed orders."))
            if not record.reference:
                raise UserError(_("Reference must be set before creating a stock picking."))
            if not record.pick_type:
                raise UserError(_("Picking Type is required to create a stock picking."))
            if not record.cntr_no:
                raise UserError(_("Container No is required to create packages."))
            # if record.stock_picking_id:
            #    raise UserError(_("Stock picking already exists for this order."))

            # Check if stock picking already exists
            existing_picking = self.env['stock.picking'].search(
                [('inbound_order_id', '=', record.id), ('state', '!=', 'cancel')], limit=1)
            if existing_picking:
                raise UserError(_("A stock picking already exists for this Inbound Order."))

            charge_of_pallet = record.project.charge_of_pallet

            # Create the stock picking
            picking = self.env['stock.picking'].create({
                'picking_type_id': record.pick_type.id,
                'location_id': record.pick_type.default_location_src_id.id,
                'location_dest_id': record.pick_type.default_location_dest_id.id,
                'origin': record.billno,
                'partner_id': record.owner.id,
                'inbound_order_id': record.id,
                'owner_id': record.owner.id,
                'bill_of_lading': record.bl_no,
                'cntrno': record.cntr_no,
                'ref_1': record.reference,
                'planning_date': record.a_date,
            })
            pallet_index = 1

            # Validate total quantity for each product
            for product in record.inbound_order_product_ids:
                # Create stock move for each product on a pallet
                for pallet in product.inbound_order_product_pallet_ids:
                    total_quantity = pallet.quantity * product.pallets
                    if total_quantity <= 0:
                        raise UserError(_("Invalid total quantity for product '%s'.") % pallet.product_id.name)
                    self.env['stock.move'].create({
                        'name': pallet.product_id.name,
                        'product_id': pallet.product_id.id,
                        'product_uom_qty': total_quantity,
                        'product_uom': pallet.product_id.uom_id.id,
                        'picking_id': picking.id,
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'inbound_order_product_pallet_id': pallet.id,
                        'description_picking': pallet.id,
                        'date_deadline': picking.planning_date + timedelta(seconds=pallet.id),
                    })

                # Create move.line for each pallet with individual packages
                for p_index in range(1, int(product.pallets) + 1):
                    package_name = f"{record.reference}-{record.cntr_no}-{str(pallet_index).zfill(4)}"
                    package = self.env['stock.quant.package'].search([('name', '=', package_name)])
                    if not package:
                        package = self.env['stock.quant.package'].create({
                            'name': package_name,
                            'package_use': 'disposable',
                        })
                    # Create stock move lines for each pallet
                    for pallet in product.inbound_order_product_pallet_ids:
                        # Check if the pallet is serial-tracked and if scanning is enabled
                        move = self.env['stock.move'].search([('inbound_order_product_pallet_id', '=', pallet.id)],
                                                             limit=1)
                        # create lot if product is lot tracked
                        lot = False
                        if pallet.product_id.tracking == 'lot':
                            lot_name = f"{record.a_date.strftime('%Y%m')}-{record.cntr_no}-{str(pallet_index).zfill(4)}"
                            lot = self.env['stock.lot'].search(
                                [('name', '=', lot_name),
                                 ('product_id', '=', pallet.product_id.id)], limit=1)
                            if not lot:
                                self.env['stock.lot'].create({
                                    'name': lot_name,
                                    'product_id': pallet.product_id.id,
                                })
                            lot = self.env['stock.lot'].search(
                                [('name', '=', lot_name),
                                 ('product_id', '=', pallet.product_id.id)], limit=1)
                        if not lot and pallet.product_id.tracking == 'lot':
                            raise UserError(
                                _("Failed to create or find lot for product '%s'.") % pallet.product_id.name)

                        if pallet.product_id.tracking == 'serial' and record.is_scan_sn:
                            for unit_index in range(1, int(pallet.quantity) + 1):
                                self.env['stock.move.line'].create({
                                    'move_id': move.id,
                                    'picking_id': picking.id,
                                    'product_id': pallet.product_id.id,
                                    'product_uom_id': pallet.product_id.uom_id.id,
                                    'quantity': 1.00,  # Planned quantity
                                    'location_id': picking.location_id.id,
                                    'location_dest_id': picking.location_dest_id.id,
                                    'result_package_id': package.id if charge_of_pallet else False,
                                })
                        else:
                            self.env['stock.move.line'].create({
                                'move_id': move.id,
                                'picking_id': picking.id,
                                'product_id': pallet.product_id.id,
                                'product_uom_id': pallet.product_id.uom_id.id,
                                'quantity': pallet.quantity,  # Planned quantity
                                'location_id': picking.location_id.id,
                                'location_dest_id': picking.location_dest_id.id,
                                'result_package_id': package.id if charge_of_pallet else False,
                                'lot_id': lot.id if lot else False,
                                'lot_name': lot.name if lot else False,
                            })

                    pallet_index += 1

            record.stock_picking_id = picking.id

        # Return a success message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Stock Picking Created'),
                'message': _('Stock picking with packages has been created successfully.'),
                'sticky': False,
            }
        }

    def action_view_stock_picking(self):
        """View the related stock picking."""
        self.ensure_one()
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['domain'] = [('inbound_order_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    @api.depends('inbound_order_product_ids')
    def _onchange_sum(self):
        """Update pallets field based on inbound order products."""
        total_pallets = sum(
            product.pallets for product in self.inbound_order_product_ids if product.is_inbound_handling)
        weight_total = sum(
            product.weight_total for product in self.inbound_order_product_ids if product.is_inbound_handling)
        self.pallets = total_pallets
        self.weight_total = weight_total
        # scanning_quantity = sum(product.quantity for product in self.inbound_order_product_ids if product.is_scanning)
        # self.scanning_quantity = scanning_quantity
        # self.is_adr = any(product.adr for product in self.inbound_order_product_ids)
        '''
        total_inbound_handling_charge = sum(
            product.inbound_handling_charge for product in self.inbound_order_product_ids)
        total_scanning_charge = sum(product.inbound_scanning_charge for product in self.inbound_order_product_ids)
       
        self.inbound_handling_charge = total_inbound_handling_charge
        self.inbound_scanning_charge = total_scanning_charge
        '''

    def action_calculate_charges(self):
        """Calculate the total charges for the inbound order."""
        for record in self:
            record.pallets = sum(
                product.pallets for product in record.inbound_order_product_ids if product.is_inbound_handling)

        '''
            record.scanning_quantity = sum(
                product.quantity for product in self.inbound_order_product_ids if product.is_scanning)
            if record.type == 'inbound':
                record.inbound_trucking_charge = record.project.inbound_trucking_charge
            for detail in record.inbound_order_product_ids:
                # Compute handling and scanning charges for each product
                detail._compute_inbound_handling_charge()
                detail._compute_inbound_scanning_charge()
            # Recalculate total charges
           
            record.inbound_handling_charge = sum(
                product.inbound_handling_charge for product in record.inbound_order_product_ids)
            record.inbound_scanning_charge = sum(
                product.inbound_scanning_charge for product in record.inbound_order_product_ids)
        '''

    def cron_update_inbound_date(self):
        """Scheduled action to update inbound dates for confirmed orders without an inbound date."""
        orders = self.search([])
        for order in orders:
            stock_picking = self.env['stock.picking'].search(
                [('inbound_order_id', '=', order.id), ('state', '!=', 'cancel')],
                order='scheduled_date asc',
                limit=1
            )

            if stock_picking:
                # Update the stock picking ID and inbound date
                order.stock_picking_id = stock_picking.id
                if stock_picking.date_done:
                    order.i_datetime = stock_picking.date_done
                    if order.status == 'planning':
                        order.status = 'inbound'
                    _logger.info("Updated i_date for order %s to %s", order.id, stock_picking.date_done)
            else:
                _logger.info("No valid stock picking found for order %s", order.id)

    # View inbound order product details
    def view_inbound_order_product_details(self):
        """Open a window to view inbound order product details."""
        self.ensure_one()
        self.env['world.depot.inbound.order.product.details'].search([('inbound_order_id', '=', self.id)]).unlink()
        for pallet in self.inbound_order_product_ids:
            mixed = False
            if len(pallet.inbound_order_product_pallet_ids) > 1:
                mixed = True
            i = 1
            for product in pallet.inbound_order_product_pallet_ids:
                pallets = pallet.pallets
                if i > 1:
                    pallets = 0
                self.env['world.depot.inbound.order.product.details'].create({
                    'inbound_order_id': self.id,
                    'cntr_no': self.cntr_no,
                    'bl_no': self.bl_no,
                    'pallet_id': pallet.id,
                    'pallets': pallets,
                    'mixed': mixed,
                    'product_id': product.product_id.id,  # Use the product ID
                    'product_name': product.product_id.name,  # Use the product name
                    'barcode': product.product_id.barcode,
                    'default_code': product.product_id.default_code,
                    'quantity': product.quantity,
                    'qty_subtotal': pallet.pallets * product.quantity,
                })
                i += 1
        return {
            'name': _('Inbound Order Product Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'world.depot.inbound.order.product.details',
            'view_mode': 'list',
            'domain': [('inbound_order_id', '=', self.id)],
            'context': {'create': False},
        }


class InboundOrderProduct(models.Model):
    _name = 'world.depot.inbound.order.product'
    _description = 'Inbound Order Product'

    inbound_order_id = fields.Many2one('world.depot.inbound.order', string='Inbound Order', required=True)
    project = fields.Many2one(related='inbound_order_id.project', string='Project', store=True, readonly=True)
    project_category_id = fields.Many2one(related='project.category', string='Project Category', store=True,
                                          readonly=True)

    pallet_type = fields.Char(string='Pallet Type', help='How many quantity on a pallet', default='')
    pallet_no = fields.Char(string='Pallet No', help='Pallet number for tracking', default='')
    pallets = fields.Float(string='Pallets', required=True, default=1.0)
    product_id = fields.Many2one('product.product', string='Product',
                                 domain="[('categ_id', '=', project_category_id)]")
    adr = fields.Boolean(string='ADR', help='Indicates if the product is classified as ADR (dangerous goods)')
    un_number = fields.Char(string='UN Number', help='United Nations number for dangerous goods classification')
    quantity = fields.Float(string='Quantity', compute='_compute_quantity', store=True, tracking=True,
                            readonly=True, )
    weight_total = fields.Float(string='Total Weight (kg)', help='Total weight of the product in kilograms',
                                default=0.0, compute='_compute_quantity', store=True, tracking=True, )
    remark = fields.Text(string='Remark')
    is_serial_tracked = fields.Boolean(string='Tracked by Serial', )
    is_inbound_handling = fields.Boolean(string='is Handling', default=True, tracking=True)
    inbound_handling_price = fields.Float(string='Handling Price', default=True, tracking=True)
    inbound_handling_unit = fields.Selection(
        string='Unit',
        selection=[
            ('pallet', 'Per Pallet'),
            ('piece', 'Per Piece')],
        readonly=True,
    )
    inbound_handling_charge = fields.Float(string='Handling Charge', default=0.0, tracking=True)
    is_scanning = fields.Boolean(string='is Scanning', default=True, tracking=True)
    inbound_scanning_price = fields.Float(string='Scanning Price', default=0.0, tracking=True)
    inbound_scanning_charge = fields.Float(string='Scanning Charge', default=0.0, tracking=True)
    product_serial_number_ids = fields.One2many('world.depot.inbound.order.product.serial.number',
                                                'inbound_order_product_id',
                                                string='Product Serial Numbers',
                                                help='List of serial numbers for the product')
    inbound_order_product_pallet_ids = fields.One2many('world.depot.inbound.order.products.pallet',
                                                       'inbound_order_product_id',
                                                       string='Products of Pallet',
                                                       help='List of inbound order products of pallet')
    product_description = fields.Text('Product Description', readonly=True, compute='_compute_product_description',
                                      help='Description of the product for sale')

    @api.onchange('pallets')
    def _onchange_pallets(self):
        self.project = self.inbound_order_id.project
        self.project_category_id = self.inbound_order_id.project.category

    # get product description from related pallets
    @api.depends('inbound_order_product_pallet_ids')
    def _compute_product_description(self):
        """Compute product description from related pallets with product name and quantity."""
        for record in self:
            if record.inbound_order_product_pallet_ids:
                record.product_description = ', '.join(
                    f"{product.product_id.name} ({product.quantity})" +
                    (f"(ADR/UN_CODE: {product.un_number})" if product.adr else "")
                    for product in record.inbound_order_product_pallet_ids
                )
            else:
                record.product_description = ''

    @api.depends('inbound_order_product_pallet_ids')
    def _compute_quantity(self):
        """Compute the total quantity based on pallets and quantity."""
        for record in self:
            record.quantity = 0.0
            record.weight_total = 0.0
            total_quantity = sum(
                pallet.quantity * record.pallets for pallet in record.inbound_order_product_pallet_ids)
            total_weight = sum(
                pallet.weight * pallet.quantity * record.pallets for pallet in record.inbound_order_product_pallet_ids)
            record.quantity = total_quantity
            record.weight_total = total_weight

    @api.model
    def cron_fill_products_to_pallets(self):
        """Scheduled action to fill all products into pallets.
        products = self.search([])
        for product in products:
            if product.product_id and product.pallets > 0 and product.quantity > 0:
                quantity_per_pallet = product.quantity / product.pallets
                # Remove existing records

                existing_records = self.env['world.depot.inbound.order.products.pallet'].search(
                    [('inbound_order_product_id', '=', product.id),
                     ('product_id', '=', product.product_id.id),
                     ('quantity', '=', product.quantity)
                     ]
                )
                if not existing_records:
                    # Create new pallet records
                    self.env['world.depot.inbound.order.products.pallet'].create({
                        'project': product.project.id,
                        'project_category_id': product.project.category.id,
                        'inbound_order_product_id': product.id,
                        'product_id': product.product_id.id,
                        'quantity': quantity_per_pallet,
                        'adr': product.adr,
                        'un_number': product.un_number,
                        'is_serial_tracked': product.is_serial_tracked,
                        'remark': product.remark,
                    })

                product._compute_product_description()  # Update product description
            """

    # get price from project

    # Compute charges based on project settings
    @api.depends('pallets', 'quantity', 'inbound_handling_price')
    def _compute_inbound_handling_charge(self):
        """Compute the inbound handling charge based on pallets, quantity, and project settings."""
        for record in self:
            record.inbound_handling_charge = 0
            record.inbound_handling_price = 0
            # if record.is_inbound_handling:
            # record.inbound_handling_price = record.inbound_order_id.project.inbound_handling_price
            # record.inbound_handling_unit = record.inbound_order_id.project.inbound_handling_per
            # if record.inbound_order_id.project.inbound_handling_per == 'pallet':
            #    record.inbound_handling_charge = record.pallets * record.inbound_order_id.project.inbound_handling_price
            # elif record.inbound_order_id.project.inbound_handling_per == 'piece':
            #    record.inbound_handling_charge = record.quantity * record.inbound_order_id.project.inbound_handling_price
            # else:
            #    record.inbound_handling_unit = False
            #    record.inbound_handling_charge = 0
            #    record.inbound_handling_price = 0

    # Compute inbound scanning charge based on quantity and project settings
    @api.depends('is_scanning', 'quantity', 'inbound_scanning_price')
    def _compute_inbound_scanning_charge(self):
        """Compute the inbound scanning charge based on quantity and project settings."""
        for record in self:
            record.inbound_scanning_charge = 0
            record.inbound_scanning_price = 0
            # if record.is_scanning:
            # record.inbound_scanning_price = record.inbound_order_id.project.inbound_scanning_price
            # record.inbound_scanning_charge = record.quantity * record.inbound_order_id.project.inbound_scanning_price
            # else:
            # record.inbound_scanning_charge = 0.0


class InboundOrderProductsOfPallet(models.Model):
    _name = 'world.depot.inbound.order.products.pallet'
    _description = 'Inbound Order Products of Pallet'

    inbound_order_product_id = fields.Many2one('world.depot.inbound.order.product', string='Inbound Order Pallet',
                                               required=True)
    project = fields.Many2one(related='inbound_order_product_id.project', string='Project', store=True, readonly=True)
    project_category_id = fields.Many2one(
        related='inbound_order_product_id.project_category_id',
        string='Project Category',
        store=True,
        readonly=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain="[('categ_id', '=', parent.project_category_id)]"
    )
    adr = fields.Boolean(string='ADR', help='Indicates if the product is classified as ADR (dangerous goods)',
                         related='product_id.is_dg', store=True, readonly=True)
    un_number = fields.Char(string='UN Number', help='United Nations number for dangerous goods classification',
                            related='product_id.un_code', store=True, readonly=True)
    quantity = fields.Float(string='Quantity', default=1.0)
    weight = fields.Float(string='Weight (kg)', help='Weight of the product in kilograms',
                          related='product_id.weight', )
    weight_subtotal = fields.Float(string='Subtotal Weight (kg)', compute='_compute_weight_subtotal', store=True)
    is_serial_tracked = fields.Boolean(string='Tracked by Serial', compute='_compute_is_serial_tracked', store=True)
    remark = fields.Text(string='Remark')

    '''
    @api.onchange('project_category_id')
    def _onchange_project_category_id(self):
        """Dynamically update the domain for product_id based on project_category_id."""
        if self.project_category_id:
            return {
                'domain': {
                    'product_id': [('categ_id', '=', self.project_category_id.id)]
                }
            }
        else:
            return {
                'domain': {
                    'product_id': []
                }
            }
    '''

    @api.depends('quantity', 'weight')
    def _compute_weight_subtotal(self):
        for record in self:
            record.weight_subtotal = record.quantity * record.weight

    @api.constrains('adr')
    def _check_adr(self):
        for record in self:
            if record.adr and not record.un_number:
                raise ValidationError(_("UN Number must be provided when ADR is selected."))

    @api.depends('product_id')
    def _compute_is_serial_tracked(self):
        for record in self:
            record.is_serial_tracked = record.product_id.tracking == 'serial'
            # record.is_scanning = record.product_id.tracking == 'serial' or record.product_id.tracking == 'lot'
            # record.inbound_handling_price = record.inbound_order_id.project.inbound_handling_price
            # record.inbound_handling_unit = record.inbound_order_id.project.inbound_handling_per
            # record.inbound_scanning_price = record.inbound_order_id.project.inbound_scanning_price


class InboundOrderProductSerialNumber(models.Model):
    _description = 'Inbound Order Product Serial Number'
    _name = 'world.depot.inbound.order.product.serial.number'

    inbound_order_product_id = fields.Many2one('world.depot.inbound.order.product', string='Inbound Order Product',
                                               required=True)
    serial_number = fields.Char(string='Serial Number', required=True, help='Serial number of the product')
    quantity = fields.Float(string='Quantity', required=True, default=1.0,
                            help='Quantity of the product with this serial number', readonly=True)


class InboundOderDocs(models.Model):
    _name = 'world.depot.inbound.order.docs'
    _description = 'world.depot.inbound.order.docs'

    doc_type = fields.Selection(
        selection=[
            ('cmr', 'CMR'),
            ('sn_details', 'SN Details'),
            ('other', 'Other Document'),
        ],
        string="Document Type",
        required=True,
        tracking=True
    )
    description = fields.Text(string='Description')
    file = fields.Binary(string='File')
    filename = fields.Char(string='File name')
    inbound_order_id = fields.Many2one(
        comodel_name='world.depot.inbound.order',
        string='Inbound Order',
        required=True
    )


class InboundOrderProductDetails(models.Model):
    _name = 'world.depot.inbound.order.product.details'
    _description = 'Inbound Order Product Details'

    inbound_order_id = fields.Many2one('world.depot.inbound.order', string='Inbound Order', required=True)
    bl_no = fields.Char(string='Bill of Lading', readonly=True)
    cntr_no = fields.Char(string='Container No', readonly=True)
    pallet_id = fields.Many2one('world.depot.inbound.order.product', string='Pallet', readonly=True)
    pallets = fields.Float(string='Pallets', readonly=True)
    mixed = fields.Boolean(string='Mixed', readonly=True)
    product_id = fields.Many2one(
        'product.product',
        string='Product'
    )
    product_name = fields.Char(string='Product Name', readonly=True)
    barcode = fields.Char(string='Barcode', readonly=True)
    default_code = fields.Char(string='Internal Reference', readonly=True)
    quantity = fields.Float(string='Pcs/Pallet', readonly=True)
    qty_subtotal = fields.Float(string='Quantity', readonly=True)
