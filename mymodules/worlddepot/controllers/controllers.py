# -*- coding: utf-8 -*-
# from odoo import http


# class Worlddepot(http.Controller):
#     @http.route('/worlddepot/worlddepot', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/worlddepot/worlddepot/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('worlddepot.listing', {
#             'root': '/worlddepot/worlddepot',
#             'objects': http.request.env['worlddepot.worlddepot'].search([]),
#         })

#     @http.route('/worlddepot/worlddepot/objects/<model("worlddepot.worlddepot"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('worlddepot.object', {
#             'object': obj
#         })

