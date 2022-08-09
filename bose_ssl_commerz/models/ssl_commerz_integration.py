# -*- coding: utf-'8' "-*-"

import logging
from werkzeug import urls
import json
import requests
from uuid import uuid4
import pprint

from odoo import api, fields, models, _, SUPERUSER_ID
from odoo.tools import float_round
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.addons.bose_ssl_commerz.controllers.ssl_commerz_controllers import SSLCommerzController
from odoo.service import common
from odoo.tools.float_utils import float_compare

version_info = common.exp_version()
server_serie = version_info.get('server_serie')

_logger = logging.getLogger(__name__)


def _partner_format_address(address1=False, address2=False):
    return ' '.join((address1 or '', address2 or '')).strip()


def _partner_split_name(partner_name):
    return [' '.join(partner_name.split()[:-1]), ' '.join(partner_name.split()[-1:])]


def create_missing_journal_for_acquirers(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['payment.acquirer']._create_missing_journal_for_acquirers()


class PaymentAcquirerSSLCommerz(models.Model):
    """ Acquirer Model. Each specific acquirer can extend the model by adding
        its own fields, using the acquirer_name as a prefix for the new fields.
        Using the required_if_provider='<name>' attribute on fields it is possible
        to have required fields that depend on a specific acquirer.

        Each acquirer has a link to an ir.ui.view record that is a template of
        a button used to display the payment form. See examples in ``payment_ingenico``
        and ``payment_paypal`` modules.

        Methods that should be added in an acquirer-specific implementation:

        - ``<name>_form_generate_values(self, reference, amount, currency,
        partner_id=False, partner_values=None, tx_custom_values=None)``:
        method that generates the values used to render the form button template.
        - ``<name>_get_form_action_url(self):``: method that returns the url of
        the button form. It is used for example in ecommerce application if you
        want to post some data to the acquirer.
        - ``<name>_compute_fees(self, amount, currency_id, country_id)``: computes
        the fees of the acquirer, using generic fields defined on the acquirer
        model (see fields definition).

        Each acquirer should also define controllers to handle communication between
        OpenERP and the acquirer. It generally consists in return urls given to the
        button form and that the acquirer uses to send the customer back after the
        transaction, with transaction details given as a POST request.

        FOR SSL Commerz:
            Checkpoint Tips:
                    - For registration in Sandbox, click the link: "https://developer.sslcommerz.com/registration/"
                    - For registration in Production, click the link: "https://signup.sslcommerz.com/register"
                    - There are two processes of integration:
                            1. SSLCOMMERZ Easy Checkout in your checkout page
                            2. Redirect the customer from your checkout page to SSLCOMMERZ Hosted page
                    - You will use three APIs of SSLCOMMERZ to complete the integration:
                            1. Create and Get Session
                            2. Receive Payment Notification (IPN)
                            3. Order Validation API
                    - You must validate your transaction and amount by calling our Order Validation API
                    - You must develop the IPN url to receive the payment notification
                    - Sometime you will get Risk payments (In response you will get risk properties, 
                            value will be 0 for safe, 1 for risky). It depends on you to provide the service or not
    """

    _inherit = 'payment.acquirer'
    
    if server_serie == '14.0':
        provider = fields.Selection(selection_add=[('sslcommerz', _(
            'SSL-Commerz'))], ondelete={'sslcommerz': 'set default'})
    else:
        provider = fields.Selection(
            selection_add=[('sslcommerz', _('SSL-Commerz'))])

    sslcommerz_store_id = fields.Char(
        'Store ID', required_if_provider='sslcommerz')
    sslcommerz_store_passwd = fields.Char('Store Pasword')


    @api.model
    def _get_sslcommerz_urls(self, environment):
        """ SSL Commerz URLS """
        if environment == 'prod':
            return {
                'sslcommerz_session_url':       'https://securepay.sslcommerz.com/gwprocess/v4/api.php',
                'sslcommerz_validation_url':    'https://securepay.sslcommerz.com/validator/api/validationserverAPI.php',
            }
        else:
            return {
                'sslcommerz_session_url':       'https://sandbox.sslcommerz.com/gwprocess/v4/api.php',
                'sslcommerz_validation_url':    'https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php',
            }

    # def sslcommerz_compute_fees(self, amount, currency_id, country_id):
    #     """ Compute paypal fees.

    #         :param float amount: the amount to pay
    #         :param integer country_id: an ID of a res.country, or None. This is
    #                                    the customer's country, to be compared to
    #                                    the acquirer company country.
    #         :return float fees: computed fees
    #     """
    #     if not self.fees_active:
    #         return 0.0
    #     country = self.env['res.country'].browse(country_id)
    #     if country and self.company_id.sudo().country_id.id == country.id:
    #         percentage = self.fees_dom_var
    #         fixed = self.fees_dom_fixed
    #     else:
    #         percentage = self.fees_int_var
    #         fixed = self.fees_int_fixed
    #     fees = (percentage / 100.0 * amount + fixed) / (1 - percentage / 100.0)
    #     return fees


    def sslcommerz_form_generate_values(self, values):
        base_url = self.env['ir.config_parameter'].sudo(
        ).get_param('web.base.url')

        print(self._context)
        print(request.__dict__)

        values["value_d"] = ""

        
        if request.session.sale_order_id:
            model_name = 'sale.order'
            order_id = self.env[model_name].sudo().search([('id','=',request.session.sale_order_id )])
            if order_id:
                values["value_a"] = "sale.order" 
                values["value_b"] = str(order_id.id)   
                values["value_c"] = str(order_id.name)
                values["value_d"] = ""

        if '/my/orders/' in request.httprequest.url:
            model_name = 'sale.order'
            order_id = request.httprequest.url.split("?")[0].split("/my/orders/")[1].replace("/transaction/","")
            print(order_id)
            order_id = self.env[model_name].sudo().search([('id','=',order_id )])
            if order_id:
                values["value_a"] = model_name
                values["value_b"] = str(order_id.id)   
                values["value_c"] = str(order_id.name)
                values["value_d"] = ""
                domain = [('reference', 'like', order_id.name)]
                tx = request.env['payment.transaction'].sudo().search(domain, order='id desc', limit=1)
                if len(tx) > 0:
                    values["value_d"] = str(tx)

        if '/my/invoices/' in request.httprequest.url or '/invoice/pay/' in request.httprequest.url:
            if '/my/invoices/' in request.httprequest.url:
                move_id = request.httprequest.url.split("?")[0].split("/my/invoices/")[1].replace("/transaction/","")
            if '/invoice/pay/' in request.httprequest.url:
                move_id = request.httprequest.url.split('/invoice/pay/')[1].replace("/form_tx/","")

            print(move_id)
            model_name = 'account.move'
            move_id = request.env[model_name].sudo().search([('id','=',move_id )])
            if move_id:
                values["value_a"] = model_name
                values["value_b"] = str(move_id.id)   
                values["value_c"] = str(move_id.name)
                values["value_d"] = ""
                domain = [('reference', 'like', move_id.name )]
                tx = request.env['payment.transaction'].sudo().search(domain, order='id desc', limit=1)
                if len(tx) > 0:
                    values["value_d"] = str(tx)


        if '/website_payment' in request.httprequest.url:
            IrSequence = self.env['ir.sequence'].sudo()
            if '?' in request.httprequest.url:
                fields = request.httprequest.url.split("?")[1].split("&")
                fields_vals ={}
                for field in fields:
                    fields_vals[field.split("=")[0]] = field.split("=")[1]
            elif 'endpoint_arguments' in request.__dict__:
                fields_vals = request.endpoint_arguments
            
            sale_seq = IrSequence.search([('code', '=', 'sale.order')]).prefix
            if fields_vals.get("reference"):
                if fields_vals.get("reference")[0:len(sale_seq)] == sale_seq:
                    print("Sale Orders-------->")
                    model_name = 'sale.order'
                    order_name = fields_vals.get("reference").split("-")[0]
                    order = request.env[model_name].sudo().search([('name', '=', order_name)])
                    values["value_a"] = model_name
                    values["value_b"] = str(order.id)   
                    values["value_c"] = str(order.name)
                    values["value_d"] = ""
                    domain = [('reference', 'like', fields_vals.get("reference"))]
                    tx = request.env['payment.transaction'].sudo().search(domain, order='id desc', limit=1)
                    if len(tx) > 0:
                        values["value_d"] = str(tx)
                else:
                    print("Not Sale Orders")
                    model_name = 'account.move'
                    order_name = fields_vals.get("reference").split("-")[0]
                    order = request.env[model_name].sudo().search([('name', '=', order_name)])
                    values["value_a"] = model_name
                    values["value_b"] = str(order.id)   
                    values["value_c"] = str(order.name)
                    values["value_d"] = ""
                    domain = [('reference', 'like', fields_vals.get("reference"))]
                    tx = request.env['payment.transaction'].sudo().search(domain, order='id desc', limit=1)
                    if len(tx) > 0:
                        values["value_d"] = str(tx)
        
        session = dict(request.session).copy()
        session_vals = {}
        req_vals = ['uid', 'login', 'session_token']
        for key,value in session.items():
            if key in req_vals:
                session_vals[key] =value
        values["value_d"] = values["value_d"] + "&session=" + str(session_vals)

        sslcommerz_tx_values = dict(values)
        sslcommerz_tx_values.update({
            'store_id': str(self.sslcommerz_store_id),
            'store_passwd': str(self.sslcommerz_store_passwd),
            'total_amount': values['amount'],
            'currency': values['currency'].name,
            'tran_id': str(uuid4()),
            'success_url': urls.url_join(base_url, SSLCommerzController._success_url),
            'cancel_url': urls.url_join(base_url, SSLCommerzController._cancel_url),
            'fail_url': urls.url_join(base_url, SSLCommerzController._fail_url),
            'ipn_url': urls.url_join(base_url, SSLCommerzController._ipn_url),
            # Parameters to Handle EMI Transaction
            'emi_option': 0,
            # 'emi_max_inst_option': 0,#3,6, 9
            # 'emi_selected_inst':  'No',
            # 'emi_allow_only':  'No',
            # Customer Information
            'cus_name': values.get('partner_first_name') + ' ' + values.get('partner_last_name'),
            'cus_email': values.get('partner_email'),
            'cus_add1': values.get('partner_address'),
            'cus_add2': '',
            'cus_city': values.get('partner_city'),
            'cus_state': values.get('partner_state').name or '',
            'cus_postcode': values.get('partner_zip'),
            'cus_country': values.get('partner_country').name,
            'cus_phone': values.get('partner_phone'),
            # Shipment Information
            'shipping_method': 'NO',
            'num_of_item':  1,
            # Product Information
            'product_name': 'test',
            'product_category': 'clothing',
            'product_profile': 'general',
        })

        response_sslc = requests.post(self._get_sslcommerz_urls(
            'test')['sslcommerz_session_url'], sslcommerz_tx_values)
        response_data = {}

        if response_sslc.status_code == 200:
            response_json = json.loads(response_sslc.text)
            if response_json['status'] == 'FAILED':
                response_data['status'] = response_json['status']
                response_data['failedreason'] = response_json['failedreason']

            response_data['status'] = response_json['status']
            response_data['sessionkey'] = response_json['sessionkey']
            response_data['GatewayPageURL'] = response_json['GatewayPageURL']
            sslcommerz_tx_values["tx_url"] = response_json['GatewayPageURL']

        else:
            response_json = json.loads(response_sslc.text)
            response_data['status'] = response_json['status']
            response_data['failedreason'] = response_json['failedreason']

        

        _logger.info('response_json =====> ' + str(response_json))
        _logger.info('response_data =====>' + str(response_data))

        # sslcommerz_tx_final_values.update({ 'tx_url' : response_data['GatewayPageURL'] })
        # self.sslcommerz_set_gateway_page_url(response_data['GatewayPageURL'])
        # pprint.p_logger.info(sslcommerz_tx_values)
        # Update tx_url
        
        sslcommerz_tx_values["response_data"] = response_data
        return sslcommerz_tx_values

    def sslcommerz_set_gateway_page_url(self, GatewayPageURL):
        self.ensure_one()
        return GatewayPageURL

    def sslcommerz_get_form_action_url(self):
        self.ensure_one()
        environment = 'prod' if self.state == 'enabled' else 'test'
        return self._get_sslcommerz_urls(environment)['sslcommerz_session_url']




    def render(self, reference, amount, currency_id, partner_id=False, values=None):
        """ Renders the form template of the given acquirer as a qWeb template.
        :param string reference: the transaction reference
        :param float amount: the amount the buyer has to pay
        :param currency_id: currency id
        :param dict partner_id: optional partner_id to fill values
        :param dict values: a dictionary of values for the transction that is
        given to the acquirer-specific method generating the form values

        All templates will receive:

         - acquirer: the payment.acquirer browse record
         - user: the current user browse record
         - currency_id: id of the transaction currency
         - amount: amount of the transaction
         - reference: reference of the transaction
         - partner_*: partner-related values
         - partner: optional partner browse record
         - 'feedback_url': feedback URL, controler that manage answer of the acquirer (without base url) -> FIXME
         - 'return_url': URL for coming back after payment validation (wihout base url) -> FIXME
         - 'cancel_url': URL if the client cancels the payment -> FIXME
         - 'error_url': URL if there is an issue with the payment -> FIXME
         - context: Odoo context

        """
        if values is None:
            values = {}

        if not self.view_template_id:
            return None

        values.setdefault('return_url', '/payment/process')
        # reference and amount
        values.setdefault('reference', reference)
        amount = float_round(amount, 2)
        values.setdefault('amount', amount)

        # currency id
        currency_id = values.setdefault('currency_id', currency_id)
        if currency_id:
            currency = self.env['res.currency'].browse(currency_id)
        else:
            currency = self.env.company.currency_id
        values['currency'] = currency

        # Fill partner_* using values['partner_id'] or partner_id argument
        partner_id = values.get('partner_id', partner_id)
        billing_partner_id = values.get('billing_partner_id', partner_id)
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
            if partner_id != billing_partner_id:
                billing_partner = self.env['res.partner'].browse(billing_partner_id)
            else:
                billing_partner = partner
            values.update({
                'partner': partner,
                'partner_id': partner_id,
                'partner_name': partner.name,
                'partner_lang': partner.lang,
                'partner_email': partner.email,
                'partner_zip': partner.zip,
                'partner_city': partner.city,
                'partner_address': _partner_format_address(partner.street, partner.street2),
                'partner_country_id': partner.country_id.id or self.env['res.company']._company_default_get().country_id.id,
                'partner_country': partner.country_id,
                'partner_phone': partner.phone,
                'partner_state': partner.state_id,
                'billing_partner': billing_partner,
                'billing_partner_id': billing_partner_id,
                'billing_partner_name': billing_partner.name,
                'billing_partner_commercial_company_name': billing_partner.commercial_company_name,
                'billing_partner_lang': billing_partner.lang,
                'billing_partner_email': billing_partner.email,
                'billing_partner_zip': billing_partner.zip,
                'billing_partner_city': billing_partner.city,
                'billing_partner_address': _partner_format_address(billing_partner.street, billing_partner.street2),
                'billing_partner_country_id': billing_partner.country_id.id,
                'billing_partner_country': billing_partner.country_id,
                'billing_partner_phone': billing_partner.phone,
                'billing_partner_state': billing_partner.state_id,
            })
        if values.get('partner_name'):
            values.update({
                'partner_first_name': _partner_split_name(values.get('partner_name'))[0],
                'partner_last_name': _partner_split_name(values.get('partner_name'))[1],
            })
        if values.get('billing_partner_name'):
            values.update({
                'billing_partner_first_name': _partner_split_name(values.get('billing_partner_name'))[0],
                'billing_partner_last_name': _partner_split_name(values.get('billing_partner_name'))[1],
            })

        # Fix address, country fields
        if not values.get('partner_address'):
            values['address'] = _partner_format_address(values.get('partner_street', ''), values.get('partner_street2', ''))
        if not values.get('partner_country') and values.get('partner_country_id'):
            values['country'] = self.env['res.country'].browse(values.get('partner_country_id'))
        if not values.get('billing_partner_address'):
            values['billing_address'] = _partner_format_address(values.get('billing_partner_street', ''), values.get('billing_partner_street2', ''))
        if not values.get('billing_partner_country') and values.get('billing_partner_country_id'):
            values['billing_country'] = self.env['res.country'].browse(values.get('billing_partner_country_id'))

        # compute fees
        fees_method_name = '%s_compute_fees' % self.provider
        if hasattr(self, fees_method_name):
            fees = getattr(self, fees_method_name)(values['amount'], values['currency_id'], values.get('partner_country_id'))
            values['fees'] = float_round(fees, 2)

        # call <name>_form_generate_values to update the tx dict with acqurier specific values
        cust_method_name = '%s_form_generate_values' % (self.provider)
        if hasattr(self, cust_method_name):
            method = getattr(self, cust_method_name)
            values = method(values)

        values.update({
            'tx_url': self._context.get('tx_url', self.get_form_action_url()),
            'submit_class': self._context.get('submit_class', 'btn btn-link'),
            'submit_txt': self._context.get('submit_txt'),
            'acquirer': self,
            'user': self.env.user,
            'context': self._context,
            'type': values.get('type') or 'form',
        })

        # How to change tx_url???????????
        print(values["tx_url"])
        if values.get("response_data"):
            if values.get("response_data").get("GatewayPageURL"):
                values.update({
                    'tx_url': values.get("response_data").get("GatewayPageURL"),
                })
        # formatted_float = "{:.2f}".format(float(values["amount"]))
        # values["amount"] = values["total_amount"] = formatted_float
        print("AFTER--------->")
        print(values["tx_url"])
        _logger.info('payment.acquirer.render: <%s> values rendered for form payment:\n%s', self.provider, pprint.pformat(values))
        return self.view_template_id._render(values, engine='ir.qweb')

class TxSslcommerz(models.Model):
    _inherit = 'payment.transaction'

    sslcommerz_txn_type = fields.Char('Transaction type')
    sslcommerz_tran_id = fields.Char('Transaction Id')
    sslcommerz_val_id = fields.Char('Validation Id')
    sslcommerz_card_no = fields.Char('Card No')
    sslcommerz_bank_tran_id = fields.Char('Bank Tran Id')
    sslcommerz_status = fields.Char('Payment Status')
    sslcommerz_card_brand = fields.Char('Card Brand')
    sslcommerz_ref = fields.Char('Payment Reference')
    sslcommerz_risk_level = fields.Char('Risk Level')
    sslcommerz_risk_title = fields.Char('Risk Title')
    sslcommerz_tran_date = fields.Char('Transaction Date')
    sslcommerz_amt = fields.Char('Amt')
    sslcommerz_store_amt = fields.Char('Store Amt')
    sslcommerz_currency = fields.Char('Payment Currency')


    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    def get_tx_values(self, tx_data, post):
        tx_data.update({
            "sslcommerz_txn_type": post.get("txn_type"),
            "sslcommerz_tran_id": post.get("tran_id"),
            "sslcommerz_val_id": post.get("val_id"),
            "sslcommerz_card_no": post.get("card_no"),
            "sslcommerz_bank_tran_id": post.get("bank_tran_id"),
            "sslcommerz_status": post.get("status"),
            "sslcommerz_card_brand": post.get("card_brand"),
            "sslcommerz_ref": post.get("reference"),
            "sslcommerz_risk_level": post.get("risk_level"),
            "sslcommerz_risk_title": post.get("risk_title"),
            "sslcommerz_tran_date": post.get("tran_date"),
            "sslcommerz_amt": post.get("amount"),
            "sslcommerz_store_amt": post.get("store_amount"),
            "sslcommerz_currency": post.get("currency"),
        })
        return tx_data
        
    @api.model
    def _sslcommerz_form_get_tx_from_data(self, data):
        _logger.info('_sslcommerz_form_get_tx_from_data')
        _logger.info('_sslcommerz_form_get_tx_from_data data =====> ', data)
        GatewayPageURL = data.get('GatewayPageURL')
        if not GatewayPageURL:
            error_msg = _('Sslcommerz: received data with missing GatewayPageURL (%s)') % (
                GatewayPageURL)
            # _logger.info(error_msg)
            raise ValidationError(error_msg)

        # find tx -> @TDENOTE use txn_id ?
        txs = self.env['payment.transaction'].search(
            [('reference', '=', GatewayPageURL)])
        if not txs or len(txs) > 1:
            error_msg = 'Sslcommerz: received data for reference %s' % (
                GatewayPageURL)
            if not txs:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        _logger.info(txs[0])
        return txs[0]

    def _sslcommerz_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        _logger.info('_sslcommerz_form_get_invalid_parameters')
        _logger.info(
            '_sslcommerz_form_get_invalid_parameters data ======> ', data)

        # TODO: txn_id: shoudl be false at draft, set afterwards, and verified with txn details
        if self.acquirer_reference and data.get('response_order_id') != self.acquirer_reference:
            invalid_parameters.append(('response_order_id', data.get(
                'response_order_id'), self.acquirer_reference))
        # check what is buyed
        if float_compare(float(data.get('charge_total', '0.0')), (self.amount), 2) != 0:
            invalid_parameters.append(
                ('charge_total', data.get('charge_total'), '%.2f' % self.amount))

        return invalid_parameters

    def _sslcommerz_form_validate(self, data):
        _logger.info('_sslcommerz_form_validate data ======>\n ', data)
        status = data.get('result')
        _logger.info(
            "-----------------form -----validate----------------------")
        _logger.info(status)
        if status == '1':
            _logger.info(
                'Validated Sslcommerz payment for tx %s: set as done' % (self.reference))
            data.update(state='done', date_validate=data.get(
                'date_stamp', fields.datetime.now()))
            # data = self.get_tx_values(tx_data, data)
            #_logger.info("---form validate----------------------")
            return self.sudo().write(data)
        else:
            error = 'Received unrecognized status for Sslcommerz payment %s: %s, set as error' % (
                self.reference, status)
            # _logger.info(error)
            data.update(state='error', state_message=error)
            return self.sudo().write(data)

    def _sslcommerz_form_feedback(self, data):
        _logger.info('_sslcommerz_form_feedback')
        _logger.info('==== data ==========', data)

    def render_sale_button(self, order, submit_txt=None, render_values=None):
        values = {
            'partner_id': order.partner_id.id,
        }
        if render_values:
            values.update(render_values)
        # Not very elegant to do that here but no choice regarding the design.
        self._log_payment_transaction_sent()
        if self.acquirer_id.id == 14:
            return self.acquirer_id.with_context(submit_class='btn btn-primary', submit_txt=submit_txt or _('Pay Now')).sudo().render(
                self.reference,
                order.amount_total,
                order.pricelist_id.currency_id.id,
                values=values,
            )
