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
Handles compatibility imports for optional dependencies and flask extensions
"""
from __future__ import absolute_import, unicode_literals

# Importing from flask.ext is deprecated, so try the new package first
try:
    import flask_fas_openid  # NOQA
except ImportError:
    from flask.ext import fas_openid as flask_fas_openid  # NOQA

try:
    import flask_wtf  # NOQA
except ImportError:
    from flask.ext import wtf as flask_wtf  # NOQA

# Pillow is an optional dependency
try:
    from PIL import Image  # NOQA
except ImportError:
    import Image  # NOQA
