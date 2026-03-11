import json
import logging
from odoo import http
from odoo.exceptions import UserError
from ..validator_token import validate_token
from odoo.http import request, Response
from ..api_logs import api_logger

_logger = logging.getLogger(__name__)


class TransferOrderAPI(http.Controller):
    def get_transfer_product_info(self, products):
        line_commands = []
        mandatory_product_fields = ['product_id', 'quantity']
        for product in products:
            for field in mandatory_product_fields:
                if field not in product:
                    raise ValueError(f'Missing mandatory field in product: {field}')
            odoo_product = request.env['product.product'].sudo().search([
                '|',
                ('barcode', '=', product['product_id']),
                ('default_code', '=', product['product_id'])
            ], limit=1)

            if not odoo_product:
                raise ValueError(f'Product not found: {product["product_id"]}')
            line_vals = {
                'product': odoo_product.id,
                'quantity': product['quantity'],
                'remark': product.get('remark', ''),
            }

            line_commands.append((0, 0, line_vals))
        return line_commands

    def get_or_create_location_type(self, code):
        if not code:
            return False
        locationType = request.env['stock.location.type'].sudo()

        location_type = locationType.search(
            [('code', '=', code)],
            limit=1
        )
        if location_type:
            return location_type.id

        location_type = locationType.create({
            'code': code,
            'name': code
        })
        return location_type.id
    # Create new transfer order
    @http.route('/world_depot/hoymiles/api/transfer/order/create', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_token

    @api_logger
    def create_transfer_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)

            # Check mandatory fields
            mandatory_fields = ['date', 't_date', 'reference', 'location_from', 'location_to']
            for field in mandatory_fields:
                if field not in data:
                    return {'success': False, 'error': f'Missing mandatory field: {field}'}

            # Validate products
            try:
                line_ids = self.get_transfer_product_info(data.get('products', []))
            except ValueError as e:
                return {'success': False, 'error': str(e)}

            # Check duplicate reference
            existing_order = request.env['world.depot.transfer.order'].sudo().search([
                ('reference', '=', data['reference']),
                ('state', '!=', 'cancel')
            ], limit=1)
            if existing_order:
                return {'success': False, 'error': f'Duplicate reference: {data["reference"]}'}
            
            #check location types
            #库位类型
            if data['location_from'] == data['location_to']:
                return {'success': False, 'error': 'From Location Type and To Location Type cannot be the same.'}

            api_user = request.api_user
            if not api_user:
                return {'success': False, 'error': 'API user not found for token'}
            
            odoo_project = api_user.project
            if not odoo_project:
                return {'success': False, 'error': 'Project not found for API user'}

            from_location_type_id = self.get_or_create_location_type(
                data.get('location_from')
            )
            to_location_type_id = self.get_or_create_location_type(
                data.get('location_to')
            )

            # Prepare order values
            order_vals = {
                'type': data.get('type', 'type1'),
                'date': data.get('date'),
                't_date': data.get('t_date', False),
                'reference': data.get('reference'),
                'remark': data.get('remark', False),
                'remark1': data.get('remark1', False),
                'project': odoo_project.id,
                'from_location_type': from_location_type_id,
                'to_location_type': to_location_type_id,
                'line_ids': line_ids,
            }


            # Create order
            order = request.env['world.depot.transfer.order'].sudo().create(order_vals)

            return {
                'success': True,
                'billno': order.billno,
                'id': order.id,
                'state': order.state
            }

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'success': False, 'error': str(e)}

    # Get transfer order details
    @http.route('/world_depot/hoymiles/api/transfer/order/get', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_token
    def get_transfer_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('billno', '=', data['billno'])] if 'billno' in data else [('id', '=', data['id'])]

            order = request.env['world.depot.transfer.order'].sudo().search(domain, limit=1)
            if not order:
                return {'error': 'Transfer order not found'}

            # Prepare response data
            result = {
                'id': order.id,
                'billno': order.billno,
                'type': order.type,
                'date': str(order.date) if order.date else None,
                't_date': str(order.t_date) if order.t_date else None,
                'state': order.state,
                'reference': order.reference,
                'project_id': order.project.id if order.project else None,
                'warehouse_id': order.warehouse.id if order.warehouse else None,
                'owner': order.owner.id if order.owner else None,
                'remark': order.remark,
                'remark1': order.remark1,
                'products': []
            }

            # Add transfer order lines
            for line in order.line_ids:
                product_data = {
                    'product_id': line.product.id,
                    'product_name': line.product.name,
                    'quantity': line.quantity,
                    'location_from': line.location_from.complete_name if line.location_from else None,
                    'location_to': line.location_to.complete_name if line.location_to else None,
                    'remark': line.remark,
                }
                result['products'].append(product_data)

            # Add documents if needed
            if order.doc_ids:
                result['documents'] = []
                for doc in order.doc_ids:
                    doc_data = {
                        'doc_type': doc.doc_type,
                        'description': doc.description,
                        'filename': doc.filename,
                    }
                    result['documents'].append(doc_data)

            # Add charges if needed
            if order.charge_ids:
                result['charges'] = []
                for charge in order.charge_ids:
                    charge_data = {
                        'charge_item': charge.charge_item_id.name,
                        'quantity': charge.quantity,
                        'unit_price': charge.unit_price,
                        'amount': charge.amount,
                        'currency': charge.currency_id.name,
                    }
                    result['charges'].append(charge_data)

            return result

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'error': str(e)}

    # Update transfer order
    @http.route('/world_depot/hoymiles/api/transfer/order/update', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_token
    def update_transfer_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('billno', '=', data['billno'])] if 'billno' in data else [('id', '=', data['id'])]

            order = request.env['world.depot.transfer.order'].sudo().search(domain, limit=1)
            if not order:
                return {'error': 'Transfer order not found'}

            # Only allow updates in 'new' state
            if order.state != 'new':
                return {'error': 'Only new orders can be modified'}

            # Update fields
            updatable_fields = [
                'date', 't_date', 'reference', 'remark', 'remark1',
                'warehouse', 'project'
            ]
            updates = {}
            for field in updatable_fields:
                if field in data:
                    updates[field] = data[field]

            # Update products structure if provided
            if 'products' in data:
                # Delete existing lines
                order.line_ids.unlink()

                # Create new product lines
                line_vals = []
                for product in data.get('products', []):
                    odoo_product = request.env['product.product'].sudo().search([
                        '|', ('barcode', '=', product['product_id']),
                        ('default_code', '=', product['product_id'])
                    ], limit=1)
                    
                    if not odoo_product:
                        return {'error': f'Product not found: {product["product_id"]}'}

                    product_line = {
                        'product_id': odoo_product.id,
                        'quantity': product['quantity'],
                        'remark': product.get('remark', ''),
                    }

                    # Add location information if provided
                    if 'location_from' in product:
                        location_from = request.env['stock.location'].sudo().search([
                            ('complete_name', 'ilike', f'%{product["location_from"]}%')
                        ], limit=1)
                        if location_from:
                            product_line['location_from'] = location_from.id

                    if 'location_to' in product:
                        location_to = request.env['stock.location'].sudo().search([
                            ('complete_name', 'ilike', f'%{product["location_to"]}%')
                        ], limit=1)
                        if location_to:
                            product_line['location_to'] = location_to.id

                    line_vals.append((0, 0, product_line))

                updates['line_ids'] = line_vals

            if updates:
                order.write(updates)

            return {'success': True, 'billno': order.billno}

        except Exception as e:
            _logger.error("API Error: %s", str(e))
            return {'error': str(e)}

    # Cancel transfer order
    @http.route('/world_depot/hoymiles/api/transfer/order/cancel', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_token
    @api_logger
    def cancel_transfer_order(self, **params):
        _logger.info(">>> ENTER cancel_transfer_order")
        try:
            data = json.loads(request.httprequest.data)
            _logger.info(">>> Request data: %s", data)
            domain = [('reference', '=', data['reference'])]

            order = request.env['world.depot.transfer.order'].sudo().search(domain, limit=1)
            if not order:
                return {'success': False, 'error': f'Transfer order {data["reference"]} not found'}

            # Use the existing cancel method
            order.action_cancel_api()
            
            return {
                'success': True,
                'billno': order.billno,
                'id': order.id,
                'state': order.state
            }

        except UserError as ue:
            _logger.exception(">>> CANCEL API REAL TRACEBACK")
            _logger.error("UserError during cancellation: %s", str(ue))
            return {'success': False, 'error': str(ue)}

        except Exception as e:
            _logger.exception(">>> CANCEL API REAL TRACEBACK")
            _logger.error("Unexpected error during cancellation: %s", str(e))
            return {'success': False, 'error': str(e)}

    # Confirm transfer order
    @http.route('/world_depot/hoymiles/api/transfer/order/confirm', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_token
    @api_logger
    def confirm_transfer_order(self, **params):
        try:
            data = json.loads(request.httprequest.data)
            domain = [('reference', '=', data['reference'])]

            order = request.env['world.depot.transfer.order'].sudo().search(domain, limit=1)
            if not order:
                return {'success': False, 'error': f'Transfer order {data["reference"]} not found'}

            # Use the existing confirm method
            order.action_cancel_api()
            
            return {
                'success': True,
                'billno': order.billno,
                'id': order.id,
                'state': order.state,
                'confirmed_by': order.confirm_user_id.name if order.confirm_user_id else None,
                'confirm_time': str(order.confirm_time_user_tz) if order.confirm_time_user_tz else None
            }

        except UserError as ue:
            _logger.error("UserError during confirmation: %s", str(ue))
            return {'success': False, 'error': str(ue)}

        except Exception as e:
            _logger.error("Unexpected error during confirmation: %s", str(e))
            return {'success': False, 'error': 'An unexpected error occurred'}