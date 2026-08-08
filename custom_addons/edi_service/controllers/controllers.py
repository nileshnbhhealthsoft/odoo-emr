# -*- coding: utf-8 -*-
# from odoo import http


# class EdiService(http.Controller):
#     @http.route('/edi_service/edi_service', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/edi_service/edi_service/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('edi_service.listing', {
#             'root': '/edi_service/edi_service',
#             'objects': http.request.env['edi_service.edi_service'].search([]),
#         })

#     @http.route('/edi_service/edi_service/objects/<model("edi_service.edi_service"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('edi_service.object', {
#             'object': obj
#         })

