from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class OutboundOrderSNDetail(models.Model):
    _name = 'world.depot.outbound.order.sn.detail'
    _description = 'Outbound Order SN Detail'
    _order = 'order_id,product_id'

    order_id = fields.Many2one('world.depot.outbound.order', string='Outbound Order', readonly=True)
    type = fields.Char(string='Type', readonly=True)
    reference = fields.Char(string='Outbound Reference', readonly=True)
    p_date = fields.Date(string='Date', readonly=True)
    project = fields.Many2one('project.project', string='Project', readonly=True)
    project_name = fields.Char(string='Project Name', readonly=True, related='project.name')
    picking_PICK = fields.Many2one('stock.picking', string='Picking', readonly=True)
    product_id = fields.Many2one('product.product', string='Product')
    product_name = fields.Char(string='Product Name', readonly=True)
    lot_id = fields.Many2one('stock.lot', string='Serial/Lot ID', readonly=True)
    lot_name = fields.Char(string='Serial/Lot Name', readonly=True)
    quantity = fields.Float(string='Quantity', readonly=True)

    def init(self):
        """Initialize the SN detail table with data from outbound orders."""
        try:
            # Clear existing data
            self.env.cr.execute(f"DELETE FROM {self._table}")

            # Fetch confirmed outbound orders with stock picking
            outbound_orders = self.env['world.depot.outbound.order'].search([
                ('state', '=', 'confirm'),
                ('picking_PICK', '!=', False),
            ])

            # Prepare data for bulk insertion
            sn_details = []
            for order in outbound_orders:
                picking = order.picking_PICK
                if picking.state == 'done':
                    moves = self.env['stock.move'].search([('picking_id', '=', picking.id)])
                    for move in moves:
                        move_lines = self.env['stock.move.line'].search([('move_id', '=', move.id)])
                        for move_line in move_lines:
                            if not move_line.product_id:
                                _logger.warning(
                                    f"Product missing for move line ID {move_line.id} in order ID {order.id}")
                                continue
                            sn_details.append({
                                'order_id': order.id,
                                'type': order.type or '',
                                'reference': order.reference or '',
                                'p_date': picking.date_done or False,
                                'project': order.project.id or False,
                                'picking_PICK': picking.id or False,
                                'product_id': move_line.product_id.id or False,
                                'product_name': move_line.product_id.name or '',
                                'lot_id': move_line.lot_id.id or False,
                                'lot_name': move_line.lot_id.name or '',
                                'quantity': move_line.quantity or 0,
                            })

            # Bulk create records
            if sn_details:
                self.env['world.depot.outbound.order.sn.detail'].create(sn_details)

        except Exception as e:
            _logger.error(f"Error initializing OutboundOrderSNDetail: {e}")
            
    @api.model
    def action_manual_refresh(self, *args, **kwargs):
        """Manual entry point to refresh the outbound order SN Detail.

        This can be called from an automated action or server action in Odoo UI.
        It simply rebuilds the summary table by calling the `init` method.
        """
        _logger.info("Manual refresh of OutboundOrderSNDetail requested")
        try:
            # Rebuild the summary
            self.init()
            _logger.info("Manual refresh completed successfully")
            return True
        except Exception as e:
            _logger.error("Manual refresh failed: %s", e, exc_info=True)
            return False        