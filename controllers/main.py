# -*- coding: utf-8 -*-

import json
import logging
import pprint
import urllib
from urllib.parse import quote_plus, urljoin
from Crypto.PublicKey import RSA
from werkzeug.utils import redirect
from odoo import http
from odoo.http import request
from odoo.addons.payment_alipay.models import func

_logger = logging.getLogger(__name__)


class AlipayController(http.Controller):
    _notify_url = '/payment/alipay/notify.html'
    _return_url = '/payment/alipay/return.html'
    https_verify_url = 'https://mapi.alipay.com/gateway.do?service=notify_verify&'
    http_verify_url = 'http://notify.alipay.com/trade/notify_query.do?'

    def _get_return_url(self, **post):
        """ Extract the return URL from the data coming from alipay. """
        return_url = post.pop('return_url', '')
        if not return_url:
            custom = json.loads(post.pop('custom', False) or '{}')
            return_url = custom.get('return_url', '/my/orders')
        return return_url

    """
     * 获取返回时的签名验证结果
     * @param post 通知返回来的参数数组
     * @返回 签名验证结果
    """

    def getSignVeryfy(self, **post):
        payment_acquirer_obj = request.env['payment.acquirer'].sudo()
        alipay_public_key =payment_acquirer_obj.search([('provider', '=', 'alipay')]).alipay_public_key

        sign_type = post['sign_type']
        sign = post.pop('sign', None)

        return func.verify(post, sign, RSA.importKey(alipay_public_key)) if sign_type == "RSA2" else False

    """
     * 获取远程服务器ATN结果,验证返回URL
     * @param $notify_id 通知校验ID
     * @return 服务器ATN结果
     * 验证结果集：
     * invalid命令参数不对 出现这个错误，请检测返回处理中partner和key是否为空 
     * true 返回正确信息
     * false 请检查防火墙或者是服务器阻止端口问题以及验证时间是否超过一分钟
    """

    def getResponse(self, notify_id):
        provider = request.env['payment.acquirer'].search([('provider', '=', 'alipay')])
        partner = provider.alipay_partner
        transport = provider.alipay_transport
        if transport == 'https':
            veryfy_url = self.https_verify_url
        else:
            veryfy_url = self.http_verify_url
        veryfy_url += 'partner=' + partner + '&notify_id=' + notify_id
        resp = urllib.request.urlopen(veryfy_url)
        data = resp.read()
        resp.close()
        return data

    """
     * 针对return_url验证消息是否是支付宝发出的合法消息
     * @返回 验证结果
    """

    def verify_data(self, **post):
        if not post:
            return False
        else:
            isSign = self.getSignVeryfy(**post)
            if isSign:
                request.env['payment.transaction'].sudo().form_feedback(post, 'alipay')
                return True
            else:
                return False

    """
     * 针对notify_url验证消息是否是支付宝发出的合法消息
     * @返回 验证结果
    """

    def _verify_data(self, **post):
        if not post:
            return False
        else:
            isSign = self.getSignVeryfy(**post)
            responseTxt = 'false'
            if post['notify_id']:
                responseTxt = self.getResponse(post['notify_id'])
            # 验证
            # $responsetTxt的结果不是true，与服务器设置问题、合作身份者ID、notify_id一分钟失效有关
            # isSign的结果不是true，与安全校验码、请求时的参数格式（如：带自定义参数等）、编码格式有关
            if responseTxt == 'true' and isSign:
                request.env['payment.transaction'].sudo().form_feedback(post, 'alipay')
                return True
            else:
                return False

    @http.route('/payment/alipay/notify.html', type='http', auth="none", methods=['POST'], csrf=False)
    def alipay_notify(self, **post):
        """ AliPay NOTIFY """
        _logger.info('Beginning Alipay notify url form_feedback with post data %s', pprint.pformat(post))  # debug
        if self._verify_data(**post):
            return 'success'
        else:
            return 'fail'

    @http.route('/payment/alipay/return.html', type='http', auth="none", methods=['GET'], csrf=False)
    def alipay_return(self, **post):
        """ AliPay RETURN """
        _logger.info('Beginning Alipay return url form_feedback with post data %s', pprint.pformat(post))  # debug
        return_url = self._get_return_url(**post)
        if self.verify_data(**post):
            return redirect(return_url)
        else:
            return "验证失败"
