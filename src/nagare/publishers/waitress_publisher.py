# --
# Copyright (c) 2014-2026 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

"""The Waitress publisher."""

import multiprocessing

from waitress import task, server, adjustments

from nagare.publishers import http_publisher

task.hop_by_hop -= {'upgrade', 'connection'}


def create_config_spec():
    types = {str: 'string', int: 'integer', adjustments.asbool: 'boolean', adjustments.asoctal: 'integer'}

    black_list = ('trusted_proxy',)

    config = adjustments.Adjustments()

    config_spec = {}

    for k, v in config._params:
        t = types.get(v)
        if (k not in black_list) and (t is not None):
            config_spec[k] = '%s(default=%r)' % (t, getattr(config, k))

    del config_spec['unix_socket']
    config_spec.update(
        {
            'trusted_proxy': 'string_list(default=list(""))',
            'host': 'string(default="127.0.0.1")',
            'ident': 'string(default="HTTP server")',
            'threads': 'string(default="%r")' % adjustments.Adjustments.threads,
            'socket': 'string(default="")',
            'unix_socket_perms': 'string(default="%o")' % adjustments.Adjustments.unix_socket_perms,
        }
    )

    return config_spec


class WSGITask(task.WSGITask):
    def get_environment(self):
        environ = super().get_environment()
        environ['ws4py.socket'] = self.channel.socket

        return environ


class Channel(server.HTTPChannel):
    task_class = WSGITask


class Publisher(http_publisher.Publisher):
    """The Waitress publisher."""

    CONFIG_SPEC = http_publisher.Publisher.CONFIG_SPEC | create_config_spec()

    def __init__(self, name, dist, threads, **config):
        """Initialization."""
        self.has_multi_threads = True

        nb_cpus = multiprocessing.cpu_count()
        threads = eval(str(threads) or '1', {}, {'NB_CPUS': nb_cpus})  # noqa: S307

        super().__init__(name, dist, threads=threads, **config)

    @property
    def endpoint(self):
        socket = self.plugin_config['socket']
        if socket:
            bind = socket
            endpoint = f'unix:{bind} -> '
        else:
            bind = '{}:{}'.format(self.plugin_config['host'], self.plugin_config['port'])
            endpoint = 'http://' + bind

        return not socket, False, bind, endpoint

    def _serve(self, app, socket, services_service, **config):
        services_service(super()._serve, app)

        if socket:
            del config['host']
            del config['port']
            config['unix_socket'] = socket

        config = {k: v for k, v in config.items() if k not in http_publisher.Publisher.CONFIG_SPEC}

        s = server.create_server(
            lambda environ, start_response: services_service(self.start_handle_request, app, environ, start_response),
            **config,
        )
        s.logger = self.logger
        s.channel_class = Channel

        s.run()
