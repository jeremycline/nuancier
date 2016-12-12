# -*- coding: utf-8 -*-

__requires__ = ['SQLAlchemy >= 0.7', 'jinja2 >= 2.4']
import pkg_resources
import os

os.environ['NUANCIER_CONFIG'] = '/etc/nuancier/nuancier.cfg'

from nuancier import app, lib


election = lib.get_election(app.db_session, 1)
lib.generate_cache(
    app.db_session,
    election,
    app.config['PICTURE_FOLDER'],
    app.config['CACHE_FOLDER'],
    app.config['THUMB_SIZE'],
)
