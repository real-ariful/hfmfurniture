# -*- coding: utf-8 -*-

import json
import requests
import werkzeug
from werkzeug import urls, utils
from odoo import http, tools, _
from odoo.exceptions import ValidationError
from odoo.service import common
from odoo.http import request
import random
import string
import logging
import re
from odoo.addons.bose_ssl_commerz.controllers.ssl_commerz_controllers import SSLCommerzController
from uuid import uuid4
from pprint import pprint
import json

_logger = logging.getLogger(__name__)

version_info = common.exp_version()
server_serie = version_info.get('server_serie')

class SslCommerzController2(http.Controller):
    # --------------------------------------------------
    # SERVER2SERVER RELATED CONTROLLERS
    # --------------------------------------------------

    @http.route(['/payment/sslcommerz/s2s/create_json_3ds'], type='json', auth='public', csrf=False)
    def sslcommerz_s2s_create_json_3ds(self, verify_validity=False, **kwargs):
        print("sslcommerz_s2s_create_json_3ds")
        token = False
        acquirer = request.env['payment.acquirer'].browse(int(kwargs.get('acquirer_id')))
        try:
            if not kwargs.get('partner_id'):
                kwargs = dict(kwargs, partner_id=request.env.user.partner_id.id)
            token = acquirer.s2s_process(kwargs)
        except ValidationError as e:
            message = e.args[0]
            if isinstance(message, dict) and 'missing_fields' in message:
                if request.env.user._is_public():
                    message = _("Please sign in to complete the payment.")
                    # uimport randompdate message if portal mode = b2b
                    if request.env['ir.config_parameter'].sudo().get_param('auth_signup.allow_uninvited', 'False').lower() == 'false':
                        message += _(" If you don't have any account, ask your salesperson to grant you a portal access. ")
                else:
                    msg = _("The transaction cannot be processed because some contact details are missing or invalid: ")
                    message = msg + ', '.join(message['missing_fields']) + '. '
                    message += _("Please complete your profile. ")

            return {
                'error': message
            }
        
        if not token:
            res = {
                'result': False,
            }
            return res

        res = {
            'result': True,
            'id': token.id,
            'short_name': token.short_name,
            '3d_secure': False,
            'verified': True, 
        }
        return res



    @http.route('/payment/sslcommerz/session', type='json', auth="none", methods=['POST'], csrf=False)
    def sslcommerz_session(self, **post):
        values = self.sslcommerz_s2s_session_generate_values(post)
        response_data = values.get("response_data")
        response_data['acquirer_state'] = post.get('acquirer_state')
        _logger.info("response_data\n" + str(response_data))
        return json.dumps(values)

    def sslcommerz_s2s_session_generate_values(self, values):
        _logger.info('values ===> ', values)
        base_url = request.env['ir.config_parameter'].sudo(
        ).get_param('web.base.url')

        sslcommerz_tx_values = dict(values)

        currency = ''
        num_of_item = 1
        product_name = ''
        product_category = ''

        if values.get('acquirer_id'):
            acquirer_id = request.env['payment.acquirer'].sudo().search(
                [('id', '=', values.get('acquirer_id'))])


        if values.get('partner_id'):
            partner = request.env['res.partner'].sudo().search(
                [('id', '=', values.get('partner_id'))])

        if values.get('pricelist_id'):
            pricelist_id = request.env['product.pricelist'].sudo().search(
                [('id', '=', int(values.get('pricelist_id')))])
            currency = pricelist_id.currency_id.name or ''

        print("Currency------->\n", currency)
        if values.get('order_id'):
            order_id = request.env['sale.order'].sudo().search(
                [('id', '=', values.get('order_id'))])

            cart = []
            if order_id:
                num_of_item = len(order_id.order_line)
                for line in order_id.order_line:
                    product_name += "," + line.product_id.name
                    # Update Cart
                    cart.append({
                        'product': line.product_id.name,
                        'quantity': line.product_uom_qty,
                        'amount': line.price_unit,
                    })
                    # product category
                    if line.product_id.categ_id:
                        product_category += "," + line.product_id.categ_id.name

                product_name = product_name.split(",")[1] if len(
                    product_name) > 0 else product_name
                product_category = product_category.split(",")[1] if len(
                    product_category) > 0 else product_category

            # sslcommerz_tx_values['cart'] = cart
            # sslcommerz_tx_values['product_amount'] = order_id.amount_untaxed
            # sslcommerz_tx_values['vat'] = order_id.amount_tax
            # sslcommerz_tx_values['discount_amount'] =  order_id.amount_tax
            # sslcommerz_tx_values['convenience_fee'] =  order_id.amount_tax

        emi_option = '0'
        if emi_option == '1':
            """1 means customer will get EMI facility for this transaction"""

        # Filtering Values
        unwanted_fields = ['data_set', 'acquirer_id', 'acquirer_state',
                           'request', 'csrf_token', 'order_name', 'order_id', 'pricelist_id']
        for key, value in values.items():
            if value == '' or value == False or key in unwanted_fields:
                del(sslcommerz_tx_values[key])

        sslcommerz_tx_values.update({
            'store_id': str(acquirer_id.sslcommerz_store_id),
            'store_passwd': str(acquirer_id.sslcommerz_store_passwd),
            'total_amount': values['total_amount'],
            'currency': 'BDT',
            'tran_id': str(uuid4()),
            'success_url': urls.url_join(base_url, SSLCommerzController._success_url),
            'cancel_url': urls.url_join(base_url, SSLCommerzController._cancel_url),
            'fail_url': urls.url_join(base_url, SSLCommerzController._fail_url),
            'ipn_url': urls.url_join(base_url, SSLCommerzController._ipn_url),
            # Parameters to Handle EMI Transaction
            'emi_option': emi_option,
            # Customer Information
            'cus_name': partner.name or values.get('partner_first_name') + ' ' + values.get('partner_last_name'),
            'cus_email': partner.email or values.get('partner_email'),
            'cus_add1': partner.street or values.get('partner_address'),
            'cus_add2': partner.street2 or '',
            'cus_city': partner.city or values.get('partner_city'),
            'cus_state': partner.state_id.name if partner.state_id != False else '' or values.get('partner_state').name or '',
            'cus_postcode': partner.zip or values.get('partner_zip'),
            'cus_country': partner.country_id.name if partner.country_id != False else '' or values.get('partner_country').name,
            'cus_phone': partner.phone or values.get('partner_phone'),
            # Shipment Information
            'shipping_method': 'NO',
            'num_of_item': num_of_item,
            # Product Information
            'product_name': product_name,
            'product_category': product_category,
            'product_profile': 'general',
        })

        
        pprint(sslcommerz_tx_values)
        
        try:
            # GET Session API Request
            response_sslc = requests.post(acquirer_id._get_sslcommerz_urls(
                'test')['sslcommerz_session_url'], sslcommerz_tx_values)
            
            response_data = {}

            if response_sslc.status_code == 200:
                response_json = json.loads(response_sslc.text)
                if response_json['status'] == 'FAILED':
                    response_data['status'] = response_json['status']
                    response_data['failedreason'] = response_json['failedreason']
                    # return response_data

                response_data['status'] = response_json['status']
                response_data['sessionkey'] = response_json['sessionkey']
                response_data['GatewayPageURL'] = response_json['GatewayPageURL']
                # return response_data

            else:
                response_json = json.loads(response_sslc.text)
                response_data['status'] = response_json['status']
                response_data['failedreason'] = response_json['failedreason']
                # return response_data

            _logger.info('response_json =====>\n' + str(response_json))
            _logger.info('response_data =====>\n' + str(response_data))

            response =  {
                "sslcommerz_tx_values" : sslcommerz_tx_values,
                "response_data" : response_data,
            }

        except Exception as e:
            response =  {
                "error" : str(e.args),
                "response_data" : {},
            }

        return response
            





    @http.route(['/payment/sslcommerz/s2s/create'], type='http', auth='public')
    def sslcommerz_checkout_s2s_create(self, **post):
        acquirer_id = int(post.get('acquirer_id'))
        acquirer = request.env['payment.acquirer'].browse(acquirer_id)
        acquirer.s2s_process(post)
        return utils.redirect("/payment/process")