# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class StockReportController(http.Controller):
    @http.route('/my/stock_report', type='http', auth='user', website=True)
    def stock_report(self, **kwargs):
        """Render the stock report with dynamic filters."""
        user = request.env.user

        # Fetch filter values from the request
        warehouse_id = kwargs.get('warehouse_id')
        location_id = kwargs.get('location_id')
        product_id = kwargs.get('product_id')

        # Build the domain based on filters
        domain = [('location_id.usage', '=', 'internal')]
        if warehouse_id:
            domain.append(('location_id.warehouse_id', '=', int(warehouse_id)))
        if location_id:
            domain.append(('location_id', '=', int(location_id)))
        if product_id:
            domain.append(('product_id', '=', int(product_id)))

        # Fetch filtered stock.quant records
        stock_quants = request.env['stock.quant'].search(domain)

        # Log fetched records for debugging
        _logger.info(
            f"Filtered Stock Quant Records: {[(quant.product_id.name, quant.location_id.name) for quant in stock_quants]}")

        # Fetch options for filters
        warehouses = request.env['stock.warehouse'].search([])
        locations = request.env['stock.location'].search([])
        products = request.env['product.product'].search([])

        return request.render('worlddepot.template_stock_report', {
            'stock_quants': stock_quants,
            'warehouses': warehouses,
            'locations': locations,
            'products': products,
            'selected_warehouse': warehouse_id,
            'selected_location': location_id,
            'selected_product': product_id,
        })

    @http.route('/my/stock_report_1', type='http', auth='user', website=True)
    def stock_report_(self, **kwargs):
        """Render the stock report tree view."""
        user = request.env.user

        # Build the domain based on filters
        domain = []

        # Fetch filtered stock.quant records
        stock_quants = request.env['stock.quant'].search(domain)

        # Log fetched records for debugging
        _logger.info(
            f"Filtered Stock Quant Records: {[(quant.product_id.name, quant.location_id.name) for quant in stock_quants]}")

        # Render the tree view dynamically
        tree_view = request.env['ir.ui.view'].render('worlddepot.view_stock_quant_tree_my', {
            'stock_quants': stock_quants,
        })

        return tree_view

    @http.route('/my/stock_report_2', type='http', auth='user', website=True)
    def stock_report_2(self, **kwargs):
        """Redirect to the action for full search functionality."""
        action = request.env.ref('worlddepot.action_stock_quant_my')
        return request.redirect(f'/web#action={action.id}')
