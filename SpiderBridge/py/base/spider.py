# TVBox Python spider base class, API-compatible with the Android (Chaquopy) host.
import json
import re
import time
from abc import ABCMeta

import requests
from lxml import etree

PROXY_BASE = 'http://127.0.0.1:9978'
_CACHE = {}


class Spider(metaclass=ABCMeta):
    siteKey = ''

    def __init__(self):
        self.extend = ''

    def init(self, extend=''): pass
    def homeContent(self, filter): return {}
    def homeVideoContent(self): return {}
    def categoryContent(self, tid, pg, filter, extend): return {}
    def detailContent(self, ids): return {}
    def searchContent(self, key, quick, pg='1'): return {}
    def playerContent(self, flag, id, vipFlags): return {}
    def liveContent(self, url): return ''
    def localProxy(self, param): return None
    def isVideoFormat(self, url): return False
    def manualVideoCheck(self): return False
    def action(self, action): return ''
    def destroy(self): pass
    def getName(self): return ''
    def getDependence(self): return []

    def regStr(self, reg, src, group=1):
        m = re.search(reg, src)
        return m.group(group) if m else ''

    def removeHtmlTags(self, src):
        return re.sub(r'<.*?>', '', src)

    def cleanText(self, src):
        return re.sub('[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', '', src)

    def fetch(self, url, params=None, cookies=None, headers=None, timeout=5, verify=True, stream=False, allow_redirects=True):
        rsp = requests.get(url, params=params, cookies=cookies, headers=headers, timeout=timeout, verify=verify, stream=stream, allow_redirects=allow_redirects)
        rsp.encoding = 'utf-8'
        return rsp

    def post(self, url, params=None, data=None, json=None, cookies=None, headers=None, timeout=5, verify=True, stream=False, allow_redirects=True):
        rsp = requests.post(url, params=params, data=data, json=json, cookies=cookies, headers=headers, timeout=timeout, verify=verify, stream=stream, allow_redirects=allow_redirects)
        rsp.encoding = 'utf-8'
        return rsp

    def html(self, content):
        return etree.HTML(content)

    def str2json(self, s):
        return json.loads(s)

    def json2str(self, s):
        return json.dumps(s, ensure_ascii=False)

    def getProxyUrl(self, local=True):
        return f'{PROXY_BASE}/proxy?do=py&siteKey={requests.utils.quote(self.siteKey)}'

    def log(self, msg):
        print(json.dumps(msg, ensure_ascii=False) if isinstance(msg, (dict, list)) else msg, flush=True)

    def getCache(self, key):
        value = _CACHE.get(key)
        if isinstance(value, dict) and value.get('expiresAt', time.time() + 1) < time.time():
            _CACHE.pop(key, None)
            return None
        return value

    def setCache(self, key, value):
        _CACHE[key] = value
        return 'succeed'

    def delCache(self, key):
        _CACHE.pop(key, None)
        return 'succeed'
