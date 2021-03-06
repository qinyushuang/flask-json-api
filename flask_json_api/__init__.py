# -*- coding: utf-8 -*-

__version__ = 0.1
__all__ = ['APIManager']

from functools import wraps
from flask import json, request


class APIManager(object):
    def __init__(self, app_or_blueprint=None, jsonp_key='callback'):
        if app_or_blueprint:
            self.init_app(app_or_blueprint)
        else:
            self.app = None

        self.encoder = JSONEncodeManager()
        self.jsonp_key = jsonp_key
        
        # 加入到这个列表里的装饰器，会在每一个 API handler 注册时应用于其上。排序靠前的装饰器会先被调用
        #
        # 修改装饰器列表不会对已经注册了的 API handler 产生影响
        #
        # APIManager 把装饰好了的 API handler 交给 flask app 之后，返回的是 *原始* 的 API handler。
        # 就是说，这个函数在被 APIManager 装饰了之后，没有任何变化。
        # 这样做使得一个 API handler 可以像调用普通函数那样调用另一个 API handler
        # 不过也要注意，若想让某个装饰器在任何时候(无论是由 flask 调用，还是由另一个 API handler 调用)都起作用
        # (像 auth 装饰器就需要这样)。
        # 就不能把它加到 APIManager 的装饰器列表里面去，只能把它作为一个普通的装饰器， 手动添加到 API handler 前
        self.decorators = []

    def init_app(self, app_or_blueprint):
        self.app = app_or_blueprint

    def __call__(self, *rules, **rule_kwargs):
        """注册新 API handler"""
        def decorator(f):
            def decorated_function(*args, **kwargs):
                return self.format_response(f(*args, **kwargs))

            for decorator in self.decorators:
                decorated_function = decorator(decorated_function)
            decorated_function = wraps(f)(decorated_function)

            for rule in rules:
                self.app.add_url_rule(rule, None, decorated_function, **rule_kwargs)

            return f
        return decorator

    def format_response(self, o):
        """把 API handler 的返回值转换成 JSON 格式的 response
        如果用户的请求参数中包含 "callback"(例如：http://url?callback=xxx)，则包装成 JSONP（可定制）
        """
        json_str = json.dumps(o, default=self.encoder)
        callback = request.args.get(self.jsonp_key, False)
        if callback:
            return str(callback) + '(' + json_str + ')', 200, {'Content-Type': 'application/javascript'}
        else:
            return json_str, 200, {'Content-Type': 'application/json'}


_predefined_json_encoders = []
_predefined_common_json_encoders = []


class JSONEncodeManager(object):
    def __init__(self):
        # 用户可以创建自定义的 encoder，以处理默认的 json encoder 无法处理的数据类型
        #
        # encoder 有两种：
        #   第一种是指定了数据类型的 encoder。
        #   只让其处理指定类型及其子类的对象
        #
        #   另一种没有指定数据类型，则每处理一个值，都会调用它。适用于一个 encoder 要处理多种数据类型的情况。
        #   这种类型的 encoder 在发现一个值不应由它来处理时，须要抛出一个 TypeError 异常，
        #   这样系统才能了解情况，并把值传给下一个 encoder
        #   否则，无论 encoder 返回什么(包括 None)，系统都会认为这个值就是正确的计算结果，并将其返回
        #
        #   指定了数据类型的 encoder 会优先调用
        self.encoders = []
        self.common_encoders = []

        self.flask_json_encoder = json.JSONEncoder()

    def register(self, encoder, target_class=None):
        if target_class:
            self.encoders.append((target_class, encoder))
        else:
            self.common_encoders.append(encoder)

    def __call__(self, o):
        encoders = []
        encoders.extend(self.encoders)
        encoders.extend(_predefined_json_encoders)
        encoders.extend(self.common_encoders)
        encoders.extend(_predefined_common_json_encoders)

        for encoder in encoders:
            if isinstance(encoder, tuple):
                if isinstance(o, encoder[0]):
                    return encoder[1](o)
            else:
                try:
                    return encoder(o)
                except TypeError:
                    pass
        return self.flask_json_encoder.default(o)