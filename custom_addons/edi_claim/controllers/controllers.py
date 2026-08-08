# -*- coding: utf-8 -*-
# from odoo import http


# class EdiClaim(http.Controller):
#     @http.route('/edi_claim/edi_claim', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/edi_claim/edi_claim/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('edi_claim.listing', {
#             'root': '/edi_claim/edi_claim',
#             'objects': http.request.env['edi_claim.edi_claim'].search([]),
#         })

#     @http.route('/edi_claim/edi_claim/objects/<model("edi_claim.edi_claim"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('edi_claim.object', {
#             'object': obj
#         })

