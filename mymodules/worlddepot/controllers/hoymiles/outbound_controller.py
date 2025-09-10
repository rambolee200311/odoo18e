import json
import logging
from odoo import http
from ..validator_token import validate_token
from odoo.http import request
from ..api_logs import api_logger

_logger = logging.getLogger(__name__)


class OutboundOrderAPI(http.Controller):
    # Create new outbound order
    @http.route('/world_depot/hoymiles/api/outbound/order/create', type='json', auth='none', methods=['POST'],
                csrf=False)
    @validate_token
    @api_logger
    def create_outbound_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)

            # Check mandatory fields
            mandatory_fields = ['p_date', 'unload_company', 'reference', 'products', 'delivery_method']
            for field in mandatory_fields:
                if field not in data:
                    return {'success': False, 'error': f'Missing mandatory field: {field}'}

            # Validate products
            mandatory_fields = ['product_id', 'quantity']
            for product in data.get('products', []):
                for field in mandatory_fields:
                    if field not in product:
                        return {'error': f'Missing mandatory field in product: {field}'}
                    odoo_product = request.env['product.template'].sudo().search(
                        ['|', ('barcode', '=', product['product_id'])
                            , ('default_code', '=', product['product_id'])],
                        limit=1)
                    if not odoo_product:
                        return {'success': False, 'error': f'Product not found: {product["product_id"]}'}

            # Check duplicate reference
            existing_order = request.env['world.depot.outbound.order'].sudo().search(
                [('reference', '=', data['reference']), ('state', '!=', 'cancel')], limit=1)
            if existing_order:
                return {'success': False, 'error': f'Duplicate reference: {data["reference"]}'}

            # create unload company if not exists
            unload_company = request.env['res.partner'].sudo().search([('name', '=', data['unload_company'])], limit=1)
            if not unload_company:
                country_id = request.env['res.country'].sudo().search(
                    ['|', ('code', '=', data.get('country')), ('name', '=', data.get('country'))], limit=1).id
                unload_company = request.env['res.partner'].sudo().create({
                    'name': data['unload_company'],
                    'is_company': True,
                    'street': data.get('street', ''),
                    'city': data.get('city', ''),
                    'zip': data.get('zip', ''),
                    'country_id': country_id or False,
                    'phone': data.get('phone', ''),
                    'mobile': data.get('mobile', ''),
                })

            odoo_project = request.env['project.project'].sudo().search([('name', '=', 'HOYMILES')], limit=1)
            # Prepare order values
            order_vals = {
                'type': data.get('type', 'outbound'),
                'project': odoo_project.id if odoo_project else False,
                'unload_company': unload_company.id,
                'reference': data['reference'],
                'outbound_order_product_ids': [],
                'p_date': data.get('p_date'),
                'remark': data.get('remark', ''),
                'remark1': data.get('remark1', ''),
                'delivery_method': data.get('delivery_method', 'truck'),
            }

            # Add products to the order
            for product in data.get('products', []):
                odoo_product = request.env['product.template'].sudo().search(
                    ['|', ('barcode', '=', product['product_id'])
                        , ('default_code', '=', product['product_id'])],
                    limit=1)
                product_vals = {
                    'product_id': odoo_product.id,
                    'quantity': product['quantity'],
                    'pallets': product.get('pallets', 0.0),
                    'remark': product.get('remark', ''),
                }
                order_vals['outbound_order_product_ids'].append((0, 0, product_vals))

            # Create the order
            order = request.env['world.depot.outbound.order'].sudo().create(order_vals)

            return {
                'success': True,
                'billno': order.billno,
                'id': order.id,
                'state': order.state
            }

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'success': False, 'error': str(e)}

    # Get outbound order details
    @http.route('/world_depot/hoymiles/api/outbound_order/get', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_token
    @api_logger
    def get_outbound_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('billno', '=', data['billno'])] if 'billno' in data else [('id', '=', data['id'])]

            order = request.env['world.depot.outbound.order'].sudo().search(domain, limit=1)
            if not order:
                return {'error': 'Order not found'}

            # Prepare response data
            result = {
                'id': order.id,
                'billno': order.billno,
                'project': order.project.name,
                'unload_company': order.unload_company.name,
                'reference': order.reference,
                'state': order.state,
                'products': [
                    {
                        'product_id': product.product_id.id,
                        'quantity': product.quantity,
                        'pallets': product.pallets,
                        'remark': product.remark,
                    }
                    for product in order.outbound_order_product_ids
                ],
            }
            return result

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'error': str(e)}

    # Update outbound order
    @http.route('/world_depot/hoymiles/api/outbound_order/update', type='json', auth='none', methods=['POST'],
                csrf=False)
    @validate_token
    @api_logger
    def update_outbound_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('billno', '=', data['billno'])] if 'billno' in data else [('id', '=', data['id'])]

            order = request.env['world.depot.outbound.order'].sudo().search(domain, limit=1)
            if not order:
                return {'error': 'Order not found'}

            # Only allow updates in 'new' state
            if order.state != 'new':
                return {'error': 'Only new orders can be modified'}

            # Update fields
            updatable_fields = ['project', 'unload_company', 'reference', 'remark']
            updates = {field: data[field] for field in updatable_fields if field in data}

            # Update products if provided
            if 'products' in data:
                order.outbound_order_product_ids.unlink()
                product_lines = []
                for product in data['products']:
                    product_lines.append((0, 0, {
                        'product_id': product['product_id'],
                        'quantity': product['quantity'],
                        'pallets': product.get('pallets', 0.0),
                        'remark': product.get('remark', ''),
                    }))
                updates['outbound_order_product_ids'] = product_lines

            if updates:
                order.write(updates)

            return {'success': True, 'billno': order.billno}

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'error': str(e)}

    # Cancel outbound order
    @http.route('/world_depot/hoymiles/api/outbound_order/cancel', type='json', auth='none', methods=['POST'],
                csrf=False)
    @validate_token
    @api_logger
    def cancel_outbound_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('billno', '=', data['billno'])] if 'billno' in data else [('id', '=', data['id'])]

            order = request.env['world.depot.outbound.order'].sudo().search(domain, limit=1)
            if not order:
                return {'error': 'Order not found'}

            if order.state != 'new':
                return {'error': 'Only new orders can be cancelled'}

            order.action_cancel()
            return {'success': True, 'state': order.state}

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'error': str(e)}
