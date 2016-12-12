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
#
"""
Utilities to make working with users easier
"""

from functools import wraps
import os

from werkzeug import secure_filename
import flask

from nuancier import lib as nuancierlib
from nuancier import app
from nuancier.compat import Image


def is_nuancier_admin(user):
    ''' Is the user a nuancier admin.
    '''
    if not user:
        return False
    if not user.cla_done or len(user.groups) < 1:
        return False

    admins = app.config['ADMIN_GROUP']
    if isinstance(admins, basestring):  # pragma: no cover
        admins = set([admins])
    else:
        admins = set(admins)

    return len(set(user.groups).intersection(admins)) > 0


def is_nuancier_reviewer(user):
    ''' Is the user a nuancier reviewer.
    '''
    if not user:
        return False
    if not user.cla_done or len(user.groups) < 1:
        return False

    reviewers = app.config['REVIEW_GROUP']
    if isinstance(reviewers, basestring):  # pragma: no cover
        reviewers = set([reviewers])
    else:  # pragma: no cover
        reviewers = set(reviewers)

    return len(set(user.groups).intersection(reviewers)) > 0


def has_weigthed_vote(user):
    ''' Has the user a weigthed vote or not.
    '''
    if not user:  # pragma: no cover
        return False
    if not user.cla_done or len(user.groups) < 1:  # pragma: no cover
        return False

    voters = app.config['WEIGHTED_GROUP']
    if isinstance(voters, basestring):  # pragma: no cover
        voters = set([voters])
    else:  # pragma: no cover
        voters = set(voters)

    return len(set(user.groups).intersection(voters)) > 0


def fas_login_required(function):
    ''' Flask decorator to ensure that the user is logged in against FAS.
    To use this decorator you need to have a function named 'auth_login'.
    Without that function the redirect if the user is not logged in will not
    work.

    '''
    @wraps(function)
    def decorated_function(*args, **kwargs):
        ''' Wrapped function actually checking if the user is logged in.
        '''
        if not hasattr(flask.g, 'fas_user') or flask.g.fas_user is None:
            return flask.redirect(flask.url_for('.login',
                                                next=flask.request.url))
        elif not flask.g.fas_user.cla_done:
            flask.flash('You must sign the CLA (Contributor License '
                        'Agreement to use nuancier', 'error')
            return flask.redirect(flask.url_for('index'))
        return function(*args, **kwargs)
    return decorated_function


def contributor_required(function):
    ''' Flask decorator to ensure that the user is logged in against FAS.

    We'll always make sure the user is CLA+1 as it's what's needed to be
    allowed to vote.
    '''
    @wraps(function)
    def decorated_function(*args, **kwargs):
        ''' Wrapped function actually checking if the user is logged in.
        '''
        if not hasattr(flask.g, 'fas_user') or flask.g.fas_user is None:
            return flask.redirect(flask.url_for('.login',
                                                next=flask.request.url))
        elif not flask.g.fas_user.cla_done:
            flask.flash('You must sign the CLA (Contributor License '
                        'Agreement to use nuancier', 'error')
            return flask.redirect(flask.url_for('index'))
        elif len(flask.g.fas_user.groups) == 0:
            flask.flash('You must be in one more group than the CLA',
                        'error')
            return flask.redirect(flask.url_for('index'))
        return function(*args, **kwargs)
    return decorated_function


def nuancier_admin_required(function):
    ''' Decorator used to check if the loged in user is a nuancier admin
    or not.
    '''
    @wraps(function)
    def decorated_function(*args, **kwargs):
        ''' Wrapped function actually checking if the user is an admin for
        nuancier.
        '''
        if not hasattr(flask.g, 'fas_user') or flask.g.fas_user is None:
            return flask.redirect(flask.url_for('.login',
                                                next=flask.request.url))
        elif not flask.g.fas_user.cla_done:
            flask.flash('You must sign the CLA (Contributor License '
                        'Agreement to use nuancier', 'error')
            return flask.redirect(flask.url_for('index'))
        elif len(flask.g.fas_user.groups) == 0:
            flask.flash(
                'You must be in one more group than the CLA', 'error')
            return flask.redirect(flask.url_for('index'))
        elif not is_nuancier_admin(flask.g.fas_user) \
                and not is_nuancier_reviewer(flask.g.fas_user):
            flask.flash(
                'You are neither an administrator or a reviewer of nuancier',
                'error')
            return flask.redirect(flask.url_for('msg'))
        else:
            return function(*args, **kwargs)
    return decorated_function


def validate_input_file(input_file):
    ''' Validate the submitted input file.

    This validation has four layers:
      - extension of the file provided
      - MIMETYPE of the file provided
      - size of the image (1600x1200 minimal)
      - ratio of the image (16:9)

    :arg input_file: a File object of the candidate submitted/uploaded and
        for which we want to check that it compliants with our expectations.
    '''

    extension = os.path.splitext(
        secure_filename(input_file.filename))[1][1:].lower()
    if extension not in app.config.get('ALLOWED_EXTENSIONS', []):
        raise nuancierlib.NuancierException(
            'The submitted candidate has the file extension "%s" which is '
            'not an allowed format' % extension)

    mimetype = input_file.mimetype.lower()
    if mimetype not in app.config.get(
            'ALLOWED_MIMETYPES', []):  # pragma: no cover
        raise nuancierlib.NuancierException(
            'The submitted candidate has the MIME type "%s" which is '
            'not an allowed MIME type' % mimetype)

    try:
        image = Image.open(input_file.stream)
    except:
        raise nuancierlib.NuancierException(
            'The submitted candidate could not be opened as an Image')
    width, height = image.size
    min_width = app.config.get('PICTURE_MIN_WIDTH', 1600)
    min_height = app.config.get('PICTURE_MIN_HEIGHT', 1200)
    if width < min_width:
        raise nuancierlib.NuancierException(
            'The submitted candidate has a width of %s pixels which is lower'
            ' than the minimum %s pixels required' % (width, min_width))
    if height < min_height:
        raise nuancierlib.NuancierException(
            'The submitted candidate has a height of %s pixels which is lower'
            ' than the minimum %s pixels required' % (height, min_height))
