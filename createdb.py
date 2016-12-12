#!/usr/bin/env python

## These two lines are needed to run on EL6
__requires__ = ['SQLAlchemy >= 0.7', 'jinja2 >= 2.4']
import pkg_resources

from nuancier import app
from nuancier.lib import model

path_alembic = None
if 'PATH_ALEMBIC_INI' in app.config \
        and app.config['PATH_ALEMBIC_INI']:
    path_alembic = app.config['PATH_ALEMBIC_INI']
model.create_tables(app.config['DB_URL'], path_alembic, True)
