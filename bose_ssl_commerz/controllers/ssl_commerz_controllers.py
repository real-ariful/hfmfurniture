# -*- coding: utf-8 -*-
###############################################################################
#    License, author and contributors information in:                         #
#    __manifest__.py file at the root folder of this module.                  #
###############################################################################

import json
import logging
import requests
import werkzeug
from werkzeug import urls

from odoo import http, fields
from odoo.http import request
from odoo.service import common

_logger = logging.getLogger(__name__)

version_info = common.exp_version()
server_serie = version_info.get('server_serie')


class SSLCommerzController(http.Controller):
    _success_url = '/payment/sslcommerz/success/'
    _fail_url = '/payment/sslcommerz/fail/'
    _cancel_url = '/payment/sslcommerz/cancel/'
    _ipn_url = '/payment/sslcommerz/ipn/'

    def _get_return_url(self, **post):
        """ Extract the return URL from the data coming from sslcommerz. """
        return_url = post.pop('return_url', '')

        if not return_url:
            return_url = '/shop/payment/validate'

        return return_url

    # Newly added
    @http.route([
        '/payment/sslcommerz/return/',
        '/payment/sslcommerz/cancel/',
    ], type='http', auth='public', csrf=False)
    def sslcommerz_form_feedback(self, **post):
        if post:
            request.env['payment.transaction'].sudo(
            ).form_feedback(post, 'sslcommerz')
        base_url = request.env['ir.config_parameter'].sudo(
        ).get_param('web.base.url')
        return request.render('bose_ssl_commerz.payment_sslcommerz_redirect', {
            'return_url': urls.url_join(base_url, "/payment/process")
        })

    def sslcommerz_validate_data(self, **post):
        """
             SSLCOMMERZ Receive Payment Notification (IPN): Validate Payment with IPN

                As IPN URL already set in panel. All the payment notification will reach through IPN prior to user return back. So it needs validation for amount and transaction properly.

                The IPN will send a POST REQUEST with below parameters. Grab the post notification with your desired platform ( PHP: $_POST)
                Once data is validated, process it.

            Doc: 'https://developer.sslcommerz.com/doc/v4/'
        """
        _logger.info(
            '**************** sslcommerz_validate_data *******************')
        res = False
        model_name = post.get('value_a') 
        rec_id = post.get('value_b') 
        reference = post.get('value_c') 
        val_id = post.get('val_id')
        tx = None

        if reference:
            domain = [('reference', 'like', reference)]
            if model_name == 'sale.order':
                domain = [('sale_order_ids', '=', int(rec_id))]

            tx = request.env['payment.transaction'].sudo().search(
                domain, order='id desc', limit=1)

        if 'payment.transaction' in post.get('value_d'):
            tx_id =  post.get('value_d').split("&")[0].replace("payment.transaction(","").replace(")", "").replace(",","")
            domain = [('id', '=', int(tx_id))]
            tx = request.env['payment.transaction'].sudo().search(
                domain, order='id desc', limit=1)

        if not tx:
            # we have seemingly received a notification for a payment that did not come from
            # odoo, acknowledge it otherwise sslcommerz will keep trying
            _logger.warning(
                'received notification for unknown payment reference')
            return False

        sslcommerz_urls = request.env['payment.acquirer']._get_sslcommerz_urls(
            tx and tx.acquirer_id and tx.acquirer_id.state or 'prod')
        validate_url = sslcommerz_urls['sslcommerz_validation_url']
        acquirer_id = request.env['payment.acquirer'].search(
            [('provider', '=', 'sslcommerz')])
        store_id = acquirer_id.sslcommerz_store_id
        store_passwd = acquirer_id.sslcommerz_store_passwd
        new_post = dict(store_id=store_id,
                        store_passwd=store_passwd, 
                        val_id=val_id)
        urequest_json = self._sslcommerz_validate_url(validate_url, new_post)
        _logger.info("\nValidation Response:\n" + str(urequest_json))

        res = ''
        txn_key = post.get("val_id")
        
        print("IPN Status: " + str(post.get('status')))
        print("Order Validation Status: " + str(urequest_json.get('status')))


        if post.get('status') == "VALID" and (urequest_json.get("status") == 'VALID' or urequest_json.get("status") == 'VALIDATED'):
            res = "status=approved&transactionKey={}".format(txn_key)

            date_validate = fields.datetime.now()
            if post.get("date_stamp"):
                date_validate = post.get('date_stamp', fields.datetime.now())

            if tx:
                session = {}
                tx_data = tx.get_tx_values({}, post)
                tx_data.update({
                    "state": "done",
                    "acquirer_reference": post.get("val_id"),
                    "type":  "validation",
                    "date": date_validate,
                })
                tx.sudo().write(tx_data)
                tx._post_process_after_done()

                if tx.sale_order_ids:
                    print("tx.sale_order_ids")
                    if float(tx.sale_order_ids[0].amount_total) == float(post.get('currency_amount')):
                        if tx.sale_order_ids[0].state != 'sale':
                            tx.sale_order_ids[0].sudo().action_confirm()
                        res += "&transaction_id=%s&sale_order_id=%s" %(tx.id, tx.sale_order_ids[0].id)

                if tx.invoice_ids:
                    print(" tx.invoice_ids")
                    if float(tx.invoice_ids[0].amount_total) == float(post.get('currency_amount')):
                        self.invoice_reg_payment(tx, post)
                        value_id = post.get("value_d")
                        if len(value_id.split("&")) > 1:
                            session = value_id.split("&")[1].replace("session=","").replace("'",'"')
                            try:
                                session = json.loads(session)
                            except Exception as e:
                                session = json.dumps(session)
                                session = json.loads(session)
                            new_session = dict(request.session).copy()
                            if session:
                                if request.session.get('uid') == None:
                                    request.session['uid'] = session.get('uid')
                                if request.session.get('login') == None:
                                    request.session['login'] = session.get('login')
                                if request.session.get('session_token') == None:
                                    request.session['session_token'] = session.get('session_token')
                        res += "&transaction_id=%s&invoice_id=%s" %(tx.id, tx.invoice_ids[0].id)

        return res


    def _sslcommerz_validate_url(self, validate_url, new_post):
        """
            Order Validation API
            Request Parameters
                PARAM NAME	    DATA TYPE	DESCRIPTION
                val_id	        string (50)	Mandatory - A Validation ID against the successful transaction which is provided by SSLCOMMERZ.
                store_id	    string (30)	Mandatory - Your SSLCOMMERZ Store ID is the integration credential which can be collected through our managers
                store_passwd	string (30)	Mandatory - Your SSLCOMMERZ Store Password is the integration credential which can be collected through our managers
                format	        string (10)	Predefined value is json or xml. This parameter is used to get the response in two different format such as json or xml. By default it returns json format.
                v	            integer (1)	Open for future use only.
                Returned Parameters
                PARAM NAME	    DATA TYPE	    DESCRIPTION
                status	        string (20)	    Transaction Status. This parameter needs to be checked before update your database as a successful transaction.
                                                VALID : A successful transaction.
                                                VALIDATED : A successful transaction but called by your end more than one.
                                                INVALID_TRANSACTION : Invalid validation id (val_id).
                ....
                ....
                risk_level	integer (1)	Transaction's Risk Level - High (1) for most risky transactions and Low (0) for safe transactions. Please hold the service and proceed to collect customer verification documents
                status	string (20)	Open for future use only.
                risk_title	string (50)	Transaction's Risk Level Description
        """
        urequest = requests.get(validate_url, new_post)
        resp = urequest.text
        urequest_json = json.loads(resp)
        return urequest_json

    def invoice_reg_payment(self, tx, post):
        """invoice_reg_payment"""
        if tx.invoice_ids[0].state != 'posted':
            tx.sale_order_ids[0].sudo().action_post()
        # Register Payment
        if tx.invoice_ids[0].amount_residual > 0 and float(tx.invoice_ids[0].amount_residual) == float(post.get('currency_amount')):
            invoice = tx.invoice_ids[0]
            AccountPayment = request.env['account.payment']
            APMethod = request.env['account.payment.method']
            payment_method_id = APMethod.sudo().search([
                ('name','=','Electronic'),
                ('code','=','electronic'),
                ('payment_type','=','inbound')
                ])

            payment_vals = {
                'amount':tx.amount,
                'currency_id':invoice.currency_id.id,
                'journal_id':tx.acquirer_id.journal_id.id,
                'date':fields.Datetime.now().date().strftime("%Y-%m-%d"),
                'payment_method_id':payment_method_id.id,
                'partner_type':'customer',
                'partner_id':invoice.partner_id.id,
                'payment_type':'inbound',
                'invoice_origin':tx.reference,
                'payment_transaction_id':tx.id,
                # 'payment_token_id':tx.reference,
                'ref':tx.reference,
                'company_id': tx.acquirer_id.company_id.id,
            }
            payment = AccountPayment.sudo().create(payment_vals)
            invoice.sudo().write({'payment_id' : payment.id})

            print("payment_vals")
            print(payment_vals)
            print(payment)
            print("-----------------------------------------")



    @http.route('/payment/sslcommerz/ipn/', type='http', auth='none', methods=['POST'], csrf=False)
    def sslcommerz_ipn(self, **post):
        """ sslcommerz ipn """
        _logger.info('****************************** /IPN')
        res = self.sslcommerz_validate_data(**post)
        return werkzeug.utils.redirect('/sslcommerz?{}'.format(res))

    @http.route('/payment/sslcommerz/success', type='http', auth="none", methods=['POST'], csrf=False)
    def sslcommerz_success(self, **post):
        """ sslcommerz Success """
        _logger.info('****************************** /success')
        return_url = self._get_return_url(**post)
        res = self.sslcommerz_validate_data(**post)


        if res:
            if 'sale_order_id' in res:
                for part in res.split("&"):
                    if part.split("=")[0] == 'sale_order_id':
                        if part.split("=")[1] != False:
                            if part.split("=")[1] != request.session.get('sale_last_order_id'):
                                request.session.update({'sale_last_order_id' : int(part.split("=")[1]) })
            if 'invoice_id' in res:
                for part in res.split("&"):
                    if part.split("=")[0] == 'invoice_id':
                        if part.split("=")[1] != False:
                            invoice_id = part.split("=")[1]
                            invoice = request.env['account.move'].sudo().browse(int(invoice_id))
                            return_url = '/my/invoices/' + invoice_id + '?access_token=%s' %invoice.access_token

            # print("res---->\n", res)
            # print("return_url---->\n", return_url)
            # print("&&&&&&&&&&&&&&&&&&&&&&&&&&&&")
            # print("session", request.session)

            return werkzeug.utils.redirect(return_url + '?{}'.format(res))
        else:
            return werkzeug.utils.redirect(self._cancel_url)


    @http.route('/payment/sslcommerz/cancel', type='http', auth="none", methods=['POST'], csrf=False)
    def sslcommerz_cancel(self, **post):
        """ When the user cancels its sslcommerz payment: GET on this route """
        _logger.info('****************************** /cancel')
        reference = post.get('val_id')
        if reference:
            sales_order_obj = request.env['sale.order']
            so_ids = sales_order_obj.sudo().search([('name', '=', reference)])
            if so_ids:
                '''return_url = '/shop/payment/get_status/' + str(so_ids[0])'''
                so = sales_order_obj.browse(so_ids[0].id)

        msg = "/sslcommerz?status=cancelled&"
        for key, value in post.items():
            msg += str(key)
            msg += '='
            msg += str(value)
            msg += '&'
        return werkzeug.utils.redirect(msg)

    # @http.route('/sslcommerz', type='http', auth='public', methods=['GET'], website=True)
    # def sslcommerz_status(self, **get):
    #     _logger.info('****************************** /SSLCOMMERZ')
    #     status = ''
    #     transactionKey = ''
    #     response_code = ''
    #     message = ''
    #     infoemail = ''
    #     if 'status' in get:
    #         status = get['status']
    #     if 'transactionKey' in get:
    #         transactionKey = get['transactionKey']
    #     if 'response_code' in get:
    #         response_code = get['response_code']
    #     if 'message' in get:
    #         message = get['message']

    #     return request.render('bose_ssl_commerz.sslcommerz_status', {'status': status, 'transactionKey': transactionKey, 'response_code': response_code, 'message': message})
