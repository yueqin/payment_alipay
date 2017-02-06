# -*- coding: utf-8 -*-

{
    'name': 'Alipay Payment Acquirer',
    'author':'yueqin-odooyun',
    'category': 'Accounting',
    'summary': 'Payment Acquirer: Alipay Implementation',
    'website':'https://odooyun.com',
    'version': '1.0',
    'description': """Alipay Payment Acquirer，支付宝支付模块，用于支付宝即时收款功能，此模块中借鉴了官方paypay模块的部分写法 """,
    'depends': ['payment'],
    'data': [
        'views/payment_views.xml',
        'views/payment_alipay_templates.xml',
        'views/account_config_settings_views.xml',
        'data/payment_acquirer_data.xml',
    ],
    'installable': True,
}
