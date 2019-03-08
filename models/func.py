# coding: utf-8

import json
from datetime import datetime
from Crypto.Signature import PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
from base64 import decodebytes, encodebytes


def _base_params(app_id, method, private_key, **kw):
    """
    传入基础api参数
    ali-pay request generator
    :param method:
    :param app_id:
    :param private_key:
    :param kwargs: dict to generate a json
    :return:
    """
    all_params = dict(
        app_id=app_id,
        method=method,
        charset="utf-8",
        sign_type="RSA2",
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        version="1.0",
        biz_content=json.dumps(kw)
    )
    all_params.update(kw)
    all_params["sign"] = sign_data(all_params, RSA.importKey(private_key))
    return all_params


def ordered_data(data):
    """
    根据ASSCi进行升序排列
    :param data:
    :return:
    """
    complex_keys = []
    for key, value in data.items():
        if isinstance(value, dict):
            complex_keys.append(key)
    for key in complex_keys:
        data[key] = json.dumps(data[key], separators=(',', ':'))
    return sorted([(k, v) for k, v in data.items()])


def sign_data(data, key):
    data.pop("sign", None)
    # 排序后的字符串
    unsigned_items = ordered_data(data)
    unsigned_string = "&".join("{0}={1}".format(k, v) for k, v in unsigned_items)
    sign = set_sign(unsigned_string.encode("utf-8"), key)
    return sign


def set_sign(unsigned_string, key):
    """
    开始计算签名
    :param unsigned_string:
    :param key:
    :return:
    """
    signer = PKCS1_v1_5.new(key)
    signature = signer.sign(SHA256.new(unsigned_string))
    # base64 编码，转换为unicode表示并移除回车
    sign = encodebytes(signature).decode("utf8").replace("\n", "")
    return sign


def _verify(raw_content, signature, key):
    signer = PKCS1_v1_5.new(key)
    digest = SHA256.new()
    digest.update(raw_content.encode("utf8"))
    if signer.verify(digest, decodebytes(signature.encode("utf8"))):
        return True
    return False


def verify(data, signature, key):
    if "sign_type" in data:
        data.pop("sign_type")
    # 排序后的字符串
    unsigned_items = ordered_data(data)
    message = "&".join(u"{}={}".format(k, v) for k, v in unsigned_items)
    return _verify(message, signature, key)
