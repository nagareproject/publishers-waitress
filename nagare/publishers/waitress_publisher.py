# --
# Copyright (c) 2008-2018 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

"""The Waitress publisher"""

import multiprocessing

from ws4py.websocket import WebSocket
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

    black_list = ('trusted_proxy', 'expose_tracebacks', 'listen')

    config_spec = {}
    for k, v in adjustments.Adjustments._params:
        t = types.get(v)
        if (k not in black_list) and (t is not None):
            config_spec[k] = '%s(default=%r)' % (t, getattr(adjustments.Adjustments, k))

    return dict(
        config_spec,
        host='string(default="127.0.0.1")',
        ident='string(default="HTTP server")',
        threads='string(default=%r)' % adjustments.Adjustments.threads,
        unix_socket='string(default="")',
        unix_socket_perms='string(default=%o)' % adjustments.Adjustments.unix_socket_perms
    )


class WSGITask(task.WSGITask):
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


class Publisher(http_publisher.Publisher):
    """The Waitress publisher"""

    CONFIG_SPEC = create_config_spec()

    def __init__(self, name, dist, threads, **config):
        """Initialization
        """
        self.has_multi_threads = True

        nb_cpus = multiprocessing.cpu_count()
        threads = eval(threads or '1', {}, {'NB_CPUS': nb_cpus})

        super(Publisher, self).__init__(name, dist, threads=threads, **config)

    @staticmethod
    def create_websocket(environ):
        return WebSocket(None) if environ.get('HTTP_UPGRADE', '') == 'websocket' else None

    def _serve(self, app, reloader_service=None, **config):
        server.logging_dispatcher.logger = self.logger

        s = server.create_server(app, **config)
        s.channel_class = Channel

        s.print_listen('Serving on http://{}:{}')
        s.run()
