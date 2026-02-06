# -*- coding: utf-8 -*-
# from odoo import http


# class WorlddepotSettlementAccount(http.Controller):
#     @http.route('/worlddepot_settlement_account/worlddepot_settlement_account', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/worlddepot_settlement_account/worlddepot_settlement_account/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('worlddepot_settlement_account.listing', {
#             'root': '/worlddepot_settlement_account/worlddepot_settlement_account',
#             'objects': http.request.env['worlddepot_settlement_account.worlddepot_settlement_account'].search([]),
#         })

#     @http.route('/worlddepot_settlement_account/worlddepot_settlement_account/objects/<model("worlddepot_settlement_account.worlddepot_settlement_account"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('worlddepot_settlement_account.object', {
#             'object': obj
#         })

