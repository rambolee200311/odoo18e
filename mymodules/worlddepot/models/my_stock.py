from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_compare
import logging

_logger = logging.getLogger(__name__)

class StockRoute(models.Model):
    _inherit = 'stock.route'
    
    disable_auto_merge = fields.Boolean(
        string='Disable Auto Merge',
        help='If checked, transfers using this route will not be automatically merged'
    )


class StockRule(models.Model):
    _inherit = 'stock.rule'

    disable_auto_merge = fields.Boolean(
        string='Disable Auto Merge',
        related='route_id.disable_auto_merge',
        store=True,
        help='If checked, transfers using this rule will not be automatically merged'
    )


class StockLot(models.Model):
    _inherit = 'stock.lot'

    bill_of_lading = fields.Char('Bill of Lading')
    cntrno = fields.Char('Container Number')


class StockLocation(models.Model):
    _inherit = 'stock.location'
    
    #是否入保税仓
    is_bonded = fields.Boolean(string='Bonded Warehouse', default=False, tracking=True)
    # 新增库位类型
    location_type=fields.Many2one(
        comodel_name='stock.location.type',
        string='Extra Type',
        help='Type of the stock location'
    )

    def _get_removal_strategy_order(self, removal_strategy):
        if removal_strategy == 'fifo':
            return 'date, id'
        return super(StockLocation, self)._get_removal_strategy_order(removal_strategy)


class StockMove(models.Model):
    _inherit = 'stock.move'

    # InboundOrderProductsOfPallet's ID
    inbound_order_product_pallet_id = fields.Integer('Inbound Order Product Pallet ID')
    nine_digit_linglong_code = fields.Char(
        string="Nine Digit Linglong Code",
        related='product_id.nine_digit_linglong_code',
        store=True
    )
    outbound_order_product_id = fields.Integer('Outbound Order ProductID')
    transfer_order_line_id = fields.Integer('Transfer Order Line ID')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    bill_of_lading = fields.Char('Bill of Lading')
    cntrno = fields.Char('Container Number')
    ref_1 = fields.Char('Reference 1', help='Additional reference field for custom use')
    ref_2 = fields.Char('Reference 2', help='Additional reference field for custom use')
    planning_date = fields.Datetime('Planning Date', help='Date when the picking is planned to be processed')
    inbound_order_id = fields.Many2one(
        comodel_name='world.depot.inbound.order',
        string='Inbound Order',
        help='Reference to the related Inbound Order',
        readonly=True
    )
    outbound_order_id = fields.Many2one(
        comodel_name='world.depot.outbound.order',
        string='Outbound Order',
        help='Reference to the related Outbound Order',
    
    )
    transfer_order_id = fields.Many2one(
        comodel_name='world.depot.transfer.order',
        string='Transfer Order',
        help='Reference to the related Transfer Order',
        readonly=True
    )
    load_ref = fields.Char(string='Loading Reference', required=False, help='Reference for the Delivery')

    # Override button_validate to add post-validation processing
    def button_validate(self):
        """
        Extended button_validate method with post-validation processing
        """
        # Perform pre-validation checks
        self._check_quantity()
        
        # Call original validation
        res = super(StockPicking, self).button_validate()
        
        # Post-validation processing
        self._post_validation_processing()
        
        return res
    
    # New method for post-validation processing
    def _post_validation_processing(self):
        """
        Handle post-validation tasks for all pickings
        """
        for picking in self:
            try:
                # Propagate Bill of Lading / Container info to lots
                picking._propagate_shipping_info_to_lots()
                
                # Update inbound orders
                picking._update_inbound_order_status()
                
                # Update outbound orders
                picking._update_outbound_order_status()
                
            except Exception as e:
                _logger.error("Error in post-validation processing for picking %s: %s", picking.name, str(e))
                # Continue with other pickings even if one fails
                
                
    # update lot's Bill of Lading / Container Number
    def _propagate_shipping_info_to_lots(self):
        """
        Propagate shipping information from picking to related lots
        """
        for move_line in self.move_line_ids:
            if (move_line.lot_id and 
                not move_line.lot_id.bill_of_lading and 
                not move_line.lot_id.cntrno):
                
                update_vals = {}
                if self.bill_of_lading:
                    update_vals['bill_of_lading'] = self.bill_of_lading
                if self.cntrno:
                    update_vals['cntrno'] = self.cntrno
                    
                if update_vals:
                    move_line.lot_id.write(update_vals)
                    
                    
    # update inbound order status and date after validation
    def _update_inbound_order_status(self):
        """
        Update inbound order status and date after validation
        """
        picking_type_code = getattr(self.picking_type_id, 'code', '')
        if picking_type_code == 'incoming' and self.inbound_order_id:
            update_vals = {
                'status': 'inbound',
            }
            if self.date_done:
                update_vals['i_date'] = self.date_done
                
            self.inbound_order_id.write(update_vals)
            
    # update outbound order status and date after validation
    def _update_outbound_order_status(self):
        """
        Update outbound order status and date after validation
        """
        picking_type_code = getattr(self.picking_type_id, 'code', '')
        
        # Case 1: Update outbound order for non-outgoing pickings (excluding internal transfers)
        if picking_type_code != 'outgoing' and self.outbound_order_id:
            self._update_non_outgoing_outbound_order()
        
        # Case 2: Update outbound order for outgoing pickings from internal transfers
        elif picking_type_code == 'outgoing':
            self._update_outgoing_from_internal_transfer()
            
            
    # update outbound order for non-outgoing pickings when no origin picking exists
    def _update_non_outgoing_outbound_order(self):
        """
        Update outbound order for non-outgoing pickings when no origin picking exists
        """
        # Only update if no origin picking found
        origin_picking = self.search([('name', '=', self.origin)], limit=1)
        if not origin_picking:
            update_vals = {'status': 'picking'}
            if self.date_done:
                update_vals['picking_PICK_date'] = self.date_done
            
            self.outbound_order_id.write(update_vals)
            
   
    # update outbound order for outgoing pickings that originate from internal transfers
    def _update_outgoing_from_internal_transfer(self):
        """
        Update outbound order for outgoing pickings that originate from internal transfers
        """
        origin_picking = self.search([('name', '=', self.origin)], limit=1)
        
        if (origin_picking and 
            origin_picking.picking_type_id and 
            getattr(origin_picking.picking_type_id, 'code', '') == 'internal' and 
            origin_picking.outbound_order_id):
            
            update_vals = {
                'picking_Out': self.id,
                'status': 'outbound',
            }
            
            if self.date_done:
                update_vals['picking_Out_date'] = self.date_done
            
            origin_picking.outbound_order_id.write(update_vals)     
                    
    # quantity validation for strict operation types
    def _check_quantity(self):
        """
        Perform quantity validation checks for strict operation types
        """
        for picking in self:
            if not picking.picking_type_id.strict_quantity_control:
                continue
                
            for move in picking.move_ids:
                if move.state in ('done', 'cancel'):
                    continue
                    
                self._validate_move_quantity(move, picking.picking_type_id)

    # validate move quantity against demand and actual done quantity
    def _validate_move_quantity(self, move, picking_type):
        """
        Validate move quantity against demand and actual done quantity
        """
        # Validate move.quantity against product_uom_qty
        if float_compare(
            float(move.quantity or 0.0), 
            move.product_uom_qty,
            precision_rounding=move.product_uom.rounding
        ) != 0:
            raise UserError(_(
                "Recorded move quantity must equal demand quantity for product %(product)s.\n"
                "Demand: %(demand_qty)s %(uom)s, Recorded: %(recorded_qty)s %(uom)s\n\n"
                "This is enforced by the operation type: %(operation_type)s"
            ) % {
                'product': move.product_id.display_name,
                'demand_qty': move.product_uom_qty,
                'uom': move.product_uom.name,
                'recorded_qty': move.quantity,
                'operation_type': picking_type.name
            })
        
        # Validate actual done quantity from move lines
        self._validate_move_lines_quantity(move, picking_type)
        
    # validate actual done quantity from move lines
    def _validate_move_lines_quantity(self, move, picking_type):
        """
        Validate actual done quantity from move lines
        """
        relevant_lines = move.move_line_ids.filtered(lambda ml: ml.state != 'cancel')
        if not relevant_lines:
            return
            
        done_qty = sum(
            ml.product_uom_id._compute_quantity(ml.quantity, move.product_uom)
            for ml in relevant_lines
        )
        
        if float_compare(
            done_qty, 
            move.product_uom_qty,
            precision_rounding=move.product_uom.rounding
        ) != 0:
            raise UserError(_(
                "Actual done quantity must equal demand quantity for product %(product)s.\n"
                "Demand: %(demand_qty)s %(uom)s, Actual done: %(actual_qty)s %(uom)s\n\n"
                "This is enforced by the operation type: %(operation_type)s"
            ) % {
                'product': move.product_id.display_name,
                'demand_qty': move.product_uom_qty,
                'uom': move.product_uom.name,
                'actual_qty': done_qty,
                'operation_type': picking_type.name
            })