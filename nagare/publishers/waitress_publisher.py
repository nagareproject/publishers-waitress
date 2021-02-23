# --
# Copyright (c) 2008-2021 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

"""The Waitress publisher"""

import multiprocessing
from functools import partial

from ws4py.websocket import WebSocket
from ws4py.server import wsgiutils
from waitress import adjustments, server, task

from nagare.server import http_publisher

task.hop_by_hop -= {'upgrade', 'connection'}


def create_config_spec():
    types = {
        str: 'string',
        int: 'integer',
        adjustments.asbool: 'boolean',
        adjustments.asoctal: 'integer'
    }

    black_list = ('trusted_proxy',)

    config = adjustments.Adjustments()

    config_spec = {}

    for k, v in config._params:
        t = types.get(v)
        if (k not in black_list) and (t is not None):
            config_spec[k] = '%s(default=%r)' % (t, getattr(config, k))

    del config_spec['unix_socket']
    config_spec.update({
        'trusted_proxy': 'list(default=list(""))',
        'host': 'string(default="127.0.0.1")',
        'ident': 'string(default="HTTP server")',
        'threads': 'string(default=%r)' % adjustments.Adjustments.threads,
        'socket': 'string(default="")',
        'unix_socket_perms': 'string(default=%o)' % adjustments.Adjustments.unix_socket_perms
    })

    return config_spec


class WSGITask(task.WSGITask):

    @property
    def close_on_finish(self):
        return False

    @close_on_finish.setter
    def close_on_finish(self, v):
        pass

    def set_websocket(self, websocket, environ):
        if websocket is not None:
            websocket.sock = self.channel
            self.channel.websocket = websocket

    def get_environment(self):
        environ = super(WSGITask, self).get_environment()
        environ['set_websocket'] = self.set_websocket

        return environ


class Channel(server.HTTPChannel):
    task_class = WSGITask

    def __init__(self, *args, **kw):
        super(Channel, self).__init__(*args, **kw)
        self.websocket = None

    def received(self, data):
        return (self.websocket.process if self.websocket else super(Channel, self).received)(data)

    def sendall(self, b):
        self.send(b)

    def handle_close(self):
        if self.websocket is not None:
            self.websocket.closed(None)
            self.websocket = None

        super(Channel, self).handle_close()


class WebSocketWSGIApplication(wsgiutils.WebSocketWSGIApplication):

    def __call__(self, environ, start_response):
        environ['ws4py.socket'] = None
        return super(WebSocketWSGIApplication, self).__call__(environ, start_response)


class Publisher(http_publisher.Publisher):
    """The Waitress publisher"""

    CONFIG_SPEC = dict(http_publisher.Publisher.CONFIG_SPEC, **create_config_spec())
    websocket_app = WebSocketWSGIApplication

    def __init__(self, name, dist, threads, **config):
        """Initialization
        """
        self.has_multi_threads = True

        nb_cpus = multiprocessing.cpu_count()
        threads = eval(str(threads) or '1', {}, {'NB_CPUS': nb_cpus})

        super(Publisher, self).__init__(name, dist, threads=threads, **config)

    @property
    def endpoint(self):
        socket = self.plugin_config['socket']
        if socket:
            bind = socket
            endpoint = 'unix:{} -> '.format(bind)
        else:
            bind = '{}:{}'.format(self.plugin_config['host'], self.plugin_config['port'])
            endpoint = 'http://' + bind

        return not socket, False, bind, endpoint

    @staticmethod
    def create_websocket(environ):
        return WebSocket(None) if environ.get('HTTP_UPGRADE', '').lower() == 'websocket' else None

    def _serve(self, app, socket, services_service, **config):
        services_service(super(Publisher, self)._serve, app)

        if socket:
            del config['host']
            del config['port']
            config['unix_socket'] = socket

        config = {k: v for k, v in config.items() if k not in http_publisher.Publisher.CONFIG_SPEC}

        s = server.create_server(partial(self.start_handle_request, app), **config)
        s.logger = self.logger
        s.channel_class = Channel

        s.run()
