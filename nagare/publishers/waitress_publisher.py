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

from waitress import adjustments
from waitress.adjustments import Adjustments
from waitress.server import logging_dispatcher, create_server
from nagare.server import http_publisher


def create_config_spec():
    types = {
        str: 'string',
        int: 'integer',
        adjustments.asbool: 'boolean',
        adjustments.asoctal: 'integer'
    }

    black_list = ('trusted_proxy', 'expose_tracebacks', 'listen')

    config_spec = {}
    for k, v in Adjustments._params:
        t = types.get(v)
        if (k not in black_list) and (t is not None):
            config_spec[k] = '%s(default=%r)' % (t, getattr(Adjustments, k))

    return dict(
        config_spec,
        host='string(default="127.0.0.1")',
        ident='string(default="HTTP server")',
        threads='string(default=%r)' % Adjustments.threads,
        unix_socket='string(default="")',
        unix_socket_perms='string(default=%o)' % Adjustments.unix_socket_perms
    )


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

    def _serve(self, app, **config):
        logging_dispatcher.logger = self.logger

        server = create_server(
            lambda environ, start_response: self.start_handle_request(app, environ, start_response),
            **config
        )

        server.print_listen('Serving on http://{}:{}')
        server.run()
