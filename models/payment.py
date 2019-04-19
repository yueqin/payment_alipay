# coding: utf-8

import json
import requests
import logging
from urllib.parse import urljoin
from odoo.exceptions import UserError
from odoo import api, fields, models, _
from .func import _base_params
from odoo.exceptions import ValidationError
from odoo.addons.payment_alipay.controllers.main import AlipayController

_logger = logging.getLogger(__name__)


class AcquirerAlipay(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('alipay', 'Alipay')])
    alipay_app_id = fields.Char('alipay_app_id', required_if_provider="alipay", groups='base.group_user')
    alipay_private_key = fields.Text('Alipay Private KEY', groups='base.group_user')
    alipay_public_key = fields.Text('Alipay Public key', groups='base.group_user')

    def _get_feature_support(self):
        """Get advanced feature support by provider.

        Each provider should add its technical in the corresponding
        key for the following features:
            * fees: support payment fees computations
            * authorize: support authorizing payment (separates
                         authorization and capture)
            * tokenize: support saving payment data in a payment.tokenize
                        object
        """
        res = super(AcquirerAlipay, self)._get_feature_support()
        res['fees'].append('weixin')
        return res

    @api.model
    def _get_alipay_urls(self, environment):
        """ Alipay URLS """
        if environment == 'prod':
            return {
                'alipay_form_url': 'https://openapi.alipay.com/gateway.do?',
            }
        else:
            return {
                'alipay_form_url': 'https://openapi.alipaydev.com/gateway.do?',
            }

    @api.multi
    def alipay_compute_fees(self, amount, currency_id, country_id):
        """ Compute Alipay fees.

            :param float amount: the amount to pay
            :param integer country_id: an ID of a res.country, or None. This is
                                       the customer's country, to be compared to
                                       the acquirer company country.
            :return float fees: computed fees
        """
        if not self.fees_active:
            return 0.0
        country = self.env['res.country'].browse(country_id)
        if country and self.company_id.country_id.id == country.id:
            percentage = self.fees_dom_var
            fixed = self.fees_dom_fixed
        else:
            percentage = self.fees_int_var
            fixed = self.fees_int_fixed
        fees = (percentage / 100.0 * amount + fixed) / (1 - percentage / 100.0)
        return fees

    @api.multi
    def alipay_form_generate_values(self, values):

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        params = _base_params(
            app_id=self.alipay_app_id,
            method='alipay.trade.page.pay',
            private_key=self.alipay_private_key,
            return_url='%s' % urljoin(base_url, AlipayController._return_url),
            notify_url='%s' % urljoin(base_url, AlipayController._notify_url),
            biz_content=json.dumps({
                'out_trade_no': values['reference'],
                'total_amount': values['amount'],
                'subject': '%s: %s' % (self.company_id.name, values['reference']),
                "product_code": "FAST_INSTANT_TRADE_PAY",
            })
        )
        values.update(params)
        order = self.env['sale.order'].sudo().search([('name', '=', values['reference'])])
        if order:
            order.state = 'sent'
        return values

    @api.multi
    def alipay_get_form_action_url(self):
        return self._get_alipay_urls(self.environment)['alipay_form_url']


class TxAlipay(models.Model):
    _inherit = 'payment.transaction'

    alipay_txn_type = fields.Char('Transaction type')

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    @api.model
    def _alipay_form_get_tx_from_data(self, data):
        reference, txn_id = data.get('out_trade_no'), data.get('trade_no')
        if not reference or not txn_id:
            error_msg = _('Alipay: received data with missing reference (%s) or txn_id (%s)') % (reference, txn_id)
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        txs = self.env['payment.transaction'].search([('reference', '=', reference)])
        if not txs or len(txs) > 1:
            error_msg = 'Alipay: received data for reference %s' % (reference)
            if not txs:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return txs[0]

    @api.multi
    def _alipay_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        return invalid_parameters

    @api.multi
    def _alipay_form_validate(self, data):
        res = {
            'acquirer_reference': data.get('trade_no')
        }

        order_id = self.env['sale.order'].sudo().search([('id', '=', self.sale_order_ids.ids[0])])
        order_id.action_confirm()

        res.update(state='done', date_validate=data.get('gmt_payment', fields.datetime.now()))
        return self.write(res)

    def alipay_action_returns_commit(self):
        """ Alipay Trade Refund """

        url = 'https://openapi.alipaydev.com/gateway.do'

        params = _base_params(
            app_id=self.acquirer_id.alipay_app_id,
            method='alipay.trade.refund',
            private_key=self.acquirer_id.alipay_private_key,
            biz_content=json.dumps({
                'out_trade_no': self.reference,
                'trade_no': self.acquirer_reference,
                'refund_amount': self.amount,
                'refund_reason': u'正常退款',
            })
        )
        response = requests.post(url, params)
        content = json.loads(response.content.decode("utf-8"))
        response_info = content["alipay_trade_refund_response"]
        # 判断code
        if response_info['code'] == '10000' and response_info['msg'] == 'Success':
            if response_info['fund_change'] == 'Y':
                # 修改退款表？
                _logger.info("alipay_pay_refund success")

                res = self.env['payment.transaction'].sudo().search(
                    [('acquirer_reference', '=', response_info['trade_no']),
                     ('reference', '=', response_info['out_trade_no'])])
                if res:
                    return True
                else:
                    return False
            elif response_info['fund_change'] == 'N':
                # 已发生过退款,账户金额未变动
                raise UserError(u'警告:支付宝已退款过')
        else:
            raise UserError(u'警告:支付宝退款失败')

    def alipay_trade_close(self, out_trade_no, trade_no=None):
        """
        统一收单交易关闭接口
        :param out_trade_no:
        :param trade_no:
        :return:
        """
        url = 'https://openapi.alipaydev.com/gateway.do'
        alipay = self.env['payment.acquirer'].search([('provider', '=', 'alipay')])

        requests.post(url, _base_params(
            app_id=alipay.alipay_app_id,
            method='alipay.trade.close',
            private_key=alipay.alipay_private_key,
            biz_content=json.dumps({
                'out_trade_no': out_trade_no,
                'trade_no': trade_no,
            })
        ))
