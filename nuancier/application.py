# -*- coding: utf-8 -*-
#
# Copyright © 2013-2014  Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions
# of the GNU General Public License v.2, or (at your option) any later
# version.  This program is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY expressed or implied, including the
# implied warranties of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.  You
# should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# Any Red Hat trademarks that are incorporated in the source
# code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission
# of Red Hat, Inc.
"""
This module handles the creation and configuration of the Flask application
object.
"""
import logging
import logging.handlers
import os
import sys

from sqlalchemy.orm import sessionmaker, scoped_session
import dogpile.cache
import flask
import sqlalchemy

try:
    import flask_fas_openid  # NOQA
except ImportError:
    from flask.ext import fas_openid as flask_fas_openid  # NOQA


def create_app(app_name='Nuancier'):
    app = flask.Flask(app_name)  # NOQA
    app.config.from_object('nuancier.default_config')
    if 'NUANCIER_CONFIG' in os.environ:  # pragma: no cover
        app.config.from_envvar('NUANCIER_CONFIG')

    app.fas = flask_fas_openid.FAS(app)
    app.wsgi_app = ReverseProxied(app.wsgi_app)
    app.cache = dogpile.cache.make_region().configure(
        app.config.get('NUANCIER_CACHE_BACKEND'),
        **app.config.get('NUANCIER_CACHE_KWARGS', {})
    )
    app.db_engine = sqlalchemy.create_engine(
        app.config['DB_URL'], echo=False, pool_recycle=3600)
    app.db_session = scoped_session(sessionmaker(bind=app.db_engine))

    return app


def default_log_config(app):
    # Set up the logger
    # Send emails for big exception
    mail_handler = logging.handlers.SMTPHandler(
        app.config.get('NUANCIER_EMAIL_SMTP_SERVER', '127.0.0.1'),
        app.config.get('NUANCIER_EMAIL_FROM', 'nobody@fedoraproject.org'),
        app.config.get('NUANCIER_EMAIL_ERROR_TO', 'admin@fedoraproject.org'),
        '[Nuancier] error')
    mail_handler.setFormatter(logging.Formatter('''
        Message type:       %(levelname)s
        Location:           %(pathname)s:%(lineno)d
        Module:             %(module)s
        Function:           %(funcName)s
        Time:               %(asctime)s

        Message:

        %(message)s
    '''))
    mail_handler.setLevel(logging.ERROR)
    if not app.debug:
        app.logger.addHandler(mail_handler)

    # Log to stderr as well
    stderr_log = logging.StreamHandler(sys.stderr)
    stderr_log.setLevel(logging.INFO)
    app.logger.addHandler(stderr_log)


class ReverseProxied(object):
    '''Wrap the application in this middleware and configure the
    front-end server to add these headers, to let you quietly bind
    this to a URL other than / and to an HTTP scheme that is
    different than what is used locally.

    In nginx:
    location /myprefix {
        proxy_pass http://192.168.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Script-Name /myprefix;
        }

    :param app: the WSGI application
    '''
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]

        server = environ.get('HTTP_X_FORWARDED_HOST', '')
        if server:
            environ['HTTP_HOST'] = server

        scheme = environ.get('HTTP_X_SCHEME', '')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        return self.app(environ, start_response)
