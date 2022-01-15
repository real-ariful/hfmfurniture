# -*- coding: utf-8 -*-
# from odoo import http


# class HfmCustom(http.Controller):
#     @http.route('/hfm_custom/hfm_custom/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/hfm_custom/hfm_custom/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('hfm_custom.listing', {
#             'root': '/hfm_custom/hfm_custom',
#             'objects': http.request.env['hfm_custom.hfm_custom'].search([]),
#         })

#     @http.route('/hfm_custom/hfm_custom/objects/<model("hfm_custom.hfm_custom"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('hfm_custom.object', {
#             'object': obj
#         })
