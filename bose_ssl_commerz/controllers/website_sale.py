# -*- coding: utf-8 -*-
###############################################################################
#    License, author and contributors information in:                         #
#    __manifest__.py file at the root folder of this module.                  #
###############################################################################


from odoo import http
from odoo.http import request
from odoo.addons.payment.controllers.portal import PaymentProcessing

import logging

_logger = logging.getLogger(__name__)


class WebsiteSale(http.Controller):

    @http.route('/shop/payment/validate', type='http', auth="public", website=True, sitemap=False)
    def payment_validate(self, transaction_id=None, sale_order_id=None, **post):
        """ Method that should be called by the server when receiving an update
        for a transaction. State at this point :

         - UDPATE ME
        """
        # Customs Additions
        sale_order_id = int(sale_order_id) if sale_order_id else None
        transaction_id = int(transaction_id) if transaction_id else None
        
        if sale_order_id is None:
            order = request.website.sale_get_order()
        else:
            order = request.env['sale.order'].sudo().browse(sale_order_id)
            assert order.id == request.session.get('sale_last_order_id')

        print("========================")
        print("/shop/payment/validate")
        print("post------->", post)
        print("transaction_id", transaction_id)
        print("sale_order_id", sale_order_id)
        print("order", order)
        print("========================")

        try:
            transaction_ids = order.transaction_ids()
        except Exception as e:
            transaction_ids = order.transaction_ids

        if transaction_id:
            tx = request.env['payment.transaction'].sudo().browse(transaction_id)
            assert tx in transaction_ids
        elif order:
            tx = order.get_portal_last_transaction()
        else:
            tx = None

        if not order or (order.amount_total and not tx):
            return request.redirect('/shop')

        if order and not order.amount_total and not tx:
            order.with_context(send_email=True).action_confirm()
            return request.redirect(order.get_portal_url())

        # clean context and session, then redirect to the confirmation page
        request.website.sale_reset()
        if tx and tx.state == 'draft':
            return request.redirect('/shop')

        PaymentProcessing.remove_payment_transaction(tx)
        return request.redirect('/shop/confirmation')
