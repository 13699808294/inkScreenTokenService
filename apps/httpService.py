import json
import os
import tornado
from tornado import httpserver, gen
from tornado import web
from tornado.options import options

from apps.user.views import TokenView
from setting.setting import DEBUG
from utils.asyncRequest import asyncTornadoRequest
from utils.baseAsync import BaseAsync
from setting.setting import ESL_CLOUD_LOCAL_HOST,ESL_CLOUD_USERNAME,ESL_CLOUD_PASSWORD
tornado.options.define('port', type=int, default=8016, help='服务器端口号')
from utils.logClient import logClient


class HttpService(BaseAsync):
    def __init__(self):
        super().__init__()
        self.callback_address_set = set()
        self.token = None
        self.baseAddress = ESL_CLOUD_LOCAL_HOST
        self.username = ESL_CLOUD_USERNAME
        self.password = ESL_CLOUD_PASSWORD
        self.timerTask=None
        self.loginUrl = self.baseAddress + '/V1/Login'
        self.urlpatterns = [
            (r'/inkScreenToken/get_token', TokenView, {'server': self}),
        ]

        app = web.Application(self.urlpatterns,
                              debug=DEBUG,
                              # autoreload=True,
                              # compiled_template_cache=False,
                              # static_hash_cache=False,
                              # serve_traceback=True,
                              static_path = os.path.join(os.path.dirname(__file__),'static'),
                              template_path = os.path.join(os.path.dirname(__file__),'template'),
                              autoescape=None,  # 全局关闭模板转义功能
                                      )
        self.ioloop.add_timeout(self.ioloop.time(),self.autoLogin)
        http_setver = httpserver.HTTPServer(app)
        http_setver.listen(options.port)

    @gen.coroutine
    def autoLogin(self,autoFlag=None):
        yield self.login()
        if autoFlag != None:
            yield logClient.tornadoInfoLog('重新获取新的token')
            self.timerTask = self.ioloop.add_timeout(self.ioloop.time() + 86400, self.autoLogin, autoFlag=1)
        else:
            if self.timerTask != None:
                yield logClient.tornadoInfoLog('中途被认为token失效')
                self.ioloop.remove_timeout(self.timerTask)
            self.timerTask = self.ioloop.add_timeout(self.ioloop.time() + 86400, self.autoLogin, autoFlag=1)

    @gen.coroutine
    def login(self):
        body = {
            'username': self.username,
            'password': self.password
        }
        url = self.loginUrl
        while True:
            result = yield asyncTornadoRequest(url, method='POST', body=body)
            if result.get('errcode') == 200:
                result_body = result.get('body')
                if result_body == None:
                    yield gen.sleep(10)
                    continue
                self.token = result_body.get('token')
                if self.token == None:
                    yield gen.sleep(10)
                    continue
                yield logClient.tornadoInfoLog('登录成功')
                break
            else:
                yield logClient.tornadoWarningLog('登录失败')
        yield self.tokenChangeHandle()

    @gen.coroutine
    def tokenChangeHandle(self):
        remove_list = []
        for client in self.callback_address_set:
            try:
                clientInfo = json.loads(client)
            except:
                remove_list.append(client)
                continue
            callback = clientInfo.get('callback')
            method = clientInfo.get('method')
            if method not in ['post','get','POST','GET'] or callback == None:
                remove_list.append(client)
                continue
            data = {
                'token':self.token
            }
            if method == 'get' or method == 'GET':
                result = yield asyncTornadoRequest(callback, method='GET', params=data)
            else:
                result = yield asyncTornadoRequest(callback, method='POST', body=data)
            if result.get('ret') == 0:
                yield logClient.tornadoInfoLog('token反推成功,{}'.format(callback))
                continue
            else:
                yield logClient.tornadoWarningLog('token反推失败,{}'.format(callback))
                remove_list.append(client)
        for client in remove_list:
            self.callback_address_set.discard(client)