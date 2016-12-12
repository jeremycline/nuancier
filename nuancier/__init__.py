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
Nuancier is a web application used to vote for supplimentary wallpapers in
Fedora.
"""
from __future__ import absolute_import, unicode_literals

# The import order matters here: the application must be imported first since
# that triggers the application's creation.
from nuancier.application import create_app, default_log_config  # NOQA

app = create_app()
default_log_config(app)

from nuancier import admin, compat, default_config, forms  # NOQA
from nuancier import lib, notifications, ui, user_utils  # NOQA


__version__ = '0.10.0'
