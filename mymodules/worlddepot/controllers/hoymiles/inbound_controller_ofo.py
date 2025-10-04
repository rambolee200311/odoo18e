import json
import logging
from odoo import http
from odoo.exceptions import UserError
from ..validator_token import validate_token
from odoo.http import request, Response
from ..api_logs import api_logger

_logger = logging.getLogger(__name__)


class InboundOrderAPIOFO(http.Controller):
    # Create new inbound order
    @http.route('/world_depot/ofoundation/api/inbound/order/create', type='json', auth='none', methods=['POST'],
                csrf=False)
    @validate_token
    @api_logger
    def create_inbound_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)

            # Check mandatory fields
            mandatory_fields = ['date', 'a_date', 'reference', 'products', 'cntr_no']
            for field in mandatory_fields:
                if field not in data:
                    return {'success': False, 'error': f'Missing mandatory field: {field}'}

            # Validate products
            mandatory_fields = ['product_id', 'quantity']
            for product in data.get('products', []):
                for field in mandatory_fields:
                    if field not in product:
                        return {'error': f'Missing mandatory field in product: {field}'}
                    odoo_product = request.env['product.product'].sudo().search(
                        ['|', ('barcode', '=', product['product_id'])
                            , ('default_code', '=', product['product_id'])],
                        limit=1)
                    if not odoo_product:
                        return {'success': False, 'error': f'Product not found: {product["product_id"]}'}

            # check duplicate reference
            existing_order = request.env['world.depot.inbound.order'].sudo().search(
                [('reference', '=', data['reference']), ('state', '!=', 'cancel')], limit=1)
            if existing_order:
                return {'success': False, 'error': f'Duplicate reference: {data["reference"]}'}

            api_user = request.api_user
            if not api_user:
                return {'success': False, 'error': 'API user not found for token'}
            odoo_project = api_user.project

            # odoo_project = request.env['project.project'].sudo().search([('name', '=', 'HOYMILES')], limit=1)
            # Prepare order vals
            order_vals = {
                'type': data.get('type', 'inbound'),
                'date': data.get('date'),
                'a_date': data.get('a_date'),
                'reference': data.get('reference'),
                'cntr_no': data.get('cntr_no', False),
                'bl_no': data.get('bl_no', False),
                'remark': data.get('remark', False),
                'remark1': data.get('remark1', False),
                'project': odoo_project.id if odoo_project else False,
                'inbound_order_product_ids': [],
            }

            # Create pallet products structure
            pallet_lines = []
            for product in data.get('products', []):
                pallet_vals = {
                    'pallet_type': product.get('pallet_type', False),
                    'pallet_no': product.get('pallet_no', False),
                    'pallets': 1,
                    'inbound_order_product_pallet_ids': [],
                }
                odoo_product = request.env['product.product'].sudo().search(
                    ['|', ('barcode', '=', product['product_id'])
                        , ('default_code', '=', product['product_id'])],
                    limit=1)
                product_vals = {
                    'product_id': odoo_product.id,
                    'quantity': product['quantity'],
                    'remark': product.get('remark', ''),
                }
                pallet_vals['inbound_order_product_pallet_ids'].append((0, 0, product_vals))

                pallet_lines.append((0, 0, pallet_vals))

            order_vals['inbound_order_product_ids'] = pallet_lines

            # Create order
            order = request.env['world.depot.inbound.order'].sudo().create(order_vals)

            return {
                'success': True,
                'billno': order.billno,
                'id': order.id,
                'state': order.state
            }

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'success': False, 'error': str(e)}

    # Get inbound order details
    @http.route('/world_depot/ofoundation/api/inbound_order/get', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_token
    def get_inbound_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('billno', '=', data['billno'])] if 'billno' in data else [('id', '=', data['id'])]

            order = request.env['world.depot.inbound.order'].sudo().search(domain, limit=1)
            if not order:
                return {'error': 'Order not found'}

            # Prepare response data
            result = {
                'id': order.id,
                'billno': order.billno,
                'type': order.type,
                'date': str(order.date) if order.date else None,
                'a_date': str(order.a_date) if order.a_date else None,
                'state': order.state,
                'status': order.status,
                'reference': order.reference,
                'cntr_no': order.cntr_no,
                'bl_no': order.bl_no,
                'project_id': order.project.id,
                'warehouse_id': order.warehouse.id if order.warehouse else None,
                'pallets': order.pallets,
                'is_adr': order.is_adr,
                'pallets_data': []  # Changed from 'products' to 'pallets_data'
            }

            # Add pallets and their products
            for pallet in order.inbound_order_product_ids:
                pallet_data = {
                    'pallet_type': pallet.pallet_type,
                    'pallet_no': pallet.pallet_no,
                    'pallets': pallet.pallets,
                    'products': []
                }

                # Add products in pallet
                for product in pallet.inbound_order_product_pallet_ids:
                    p_data = {
                        'product_id': product.product_id.id,
                        'quantity': product.quantity,
                        'adr': product.adr,
                        'un_number': product.un_number,
                    }
                    pallet_data['products'].append(p_data)

                result['pallets_data'].append(pallet_data)

            return result

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'error': str(e)}

    # Update inbound order
    @http.route('/world_depot/ofoundation/api/inbound_order/update', type='json', auth='none', methods=['POST'],
                csrf=False)
    @validate_token
    def update_inbound_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('billno', '=', data['billno'])] if 'billno' in data else [('id', '=', data['id'])]

            order = request.env['world.depot.inbound.order'].sudo().search(domain, limit=1)
            if not order:
                return {'error': 'Order not found'}

            # Only allow updates in 'new' state
            if order.state != 'new':
                return {'error': 'Only new orders can be modified'}

            # Update fields
            updatable_fields = [
                'date', 'a_date', 'reference', 'cntr_no', 'bl_no',
                'remark', 'is_adr', 'warehouse', 'project'
            ]
            updates = {}
            for field in updatable_fields:
                if field in data:
                    updates[field] = data[field]

            # Update pallets structure if provided
            if 'pallets' in data:
                # Delete existing pallet lines
                order.inbound_order_product_ids.unlink()

                # Create new pallet structure
                pallet_lines = []
                for pallet in data.get('pallets', []):
                    pallet_vals = {
                        'pallet_type': pallet.get('pallet_type', ''),
                        'pallet_no': pallet.get('pallet_no', ''),
                        'pallets': pallet['pallets'],
                        'inbound_order_product_pallet_ids': []
                    }

                    # Add products to pallet
                    for product in pallet.get('products', []):
                        product_vals = {
                            'product_id': product['product_id'],
                            'quantity': product['quantity'],
                            'adr': product.get('adr', False),
                            'un_number': product.get('un_number', False),
                        }
                        pallet_vals['inbound_order_product_pallet_ids'].append((0, 0, product_vals))

                    pallet_lines.append((0, 0, pallet_vals))

                updates['inbound_order_product_ids'] = pallet_lines

            if updates:
                order.write(updates)

            return {'success': True, 'billno': order.billno}

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'error': str(e)}

    # Cancel inbound order (unchanged)
    @http.route('/world_depot/ofoundation/api/inbound/order/cancel', type='json', auth='none', methods=['POST'],
                csrf=False)
    @validate_token
    @api_logger
    def cancel_inbound_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('reference', '=', data['reference'])]

            order = request.env['world.depot.inbound.order'].sudo().search(domain, limit=1)
            if not order:
                return {'success': False, 'error': 'Order %s not found' % data['reference']}

            order.action_cancel()
            return {'success': True,
                    'billno': order.billno,
                    'id': order.id,
                    'state': order.state}

        except UserError as ue:
            _logger.error("UserError during cancellation: %s", str(ue))
            return {'success': False, 'error': str(ue)}

        except Exception as e:
            _logger.error("Unexpected error during cancellation: %s", str(e))
            return {'success': False, 'error': 'An unexpected error occurred'}
