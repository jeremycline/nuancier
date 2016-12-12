# -*- coding: utf-8 -*-
#
# Copyright © 2013  Red Hat, Inc.
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

'''
User interface for the nuancier flask application.
'''

import hashlib
import os
import random
import urlparse

from sqlalchemy.exc import SQLAlchemyError
from werkzeug import secure_filename
import flask

from nuancier import app
from nuancier.compat import Image
from nuancier import forms
from nuancier.user_utils import (fas_login_required, contributor_required,
                                 has_weigthed_vote)
import nuancier.lib as nuancierlib

# Some of the object we use here have inherited methods which apparently
# pylint does not detect.
# pylint: disable=E1101, E1103
# Ignore too many return statements
# pylint: disable=R0911


def _validate_input_file(input_file):
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
    if mimetype not in app.config.get('ALLOWED_MIMETYPES', []):
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


def _is_safe_url(target):
    """ Checks that the target url is safe and sending to the current
    website not some other malicious one.
    """
    ref_url = urlparse.urlparse(flask.request.host_url)
    test_url = urlparse.urlparse(
        urlparse.urljoin(flask.request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
        ref_url.netloc == test_url.netloc


@app.route('/')
def index():
    ''' Display the index page. '''
    elections = nuancierlib.get_elections_open(app.db_session)
    contributions = nuancierlib.get_elections_to_contribute(app.db_session)
    published = nuancierlib.get_elections_public(app.db_session)
    election = election_results = None
    if published:
        election = published[0]
        election_results = nuancierlib.get_results(app.db_session, election.id)
    return flask.render_template(
        'index.html',
        elections=elections,
        election=election,
        results=election_results,
        contributions=contributions)


@app.route('/contribute/')
def contribute_index():
    ''' Display the index page for interested contributor. '''
    elections = nuancierlib.get_elections_to_contribute(app.db_session)
    return flask.render_template(
        'contribute_index.html',
        elections=elections)


@app.route('/contribute/<election_id>', methods=['GET', 'POST'])
@fas_login_required
def contribute(election_id):
    ''' Display the index page for interested contributor. '''
    election = nuancierlib.get_election(app.db_session, election_id)
    if not election:
        flask.flash('No election found', 'error')
        return flask.render_template('msg.html')
    elif not election.submission_open:
        flask.flash('This election is not open for submission', 'error')
        return flask.redirect(flask.url_for('elections_list'))

    candidates = nuancierlib.model.Candidates.get_by_submitter(
        app.db_session, flask.g.fas_user.username, election_id)
    if election.user_n_candidates and \
            len(candidates) >= election.user_n_candidates:
        flask.flash(
            'You have uploaded the maximum number of candidates (%s) you '
            'can upload for this election' % election.user_n_candidates,
            'error')
        return flask.redirect(flask.url_for('elections_list'))

    form = forms.AddCandidateForm()
    if form.validate_on_submit():
        candidate_file = flask.request.files['candidate_file']

        try:
            _validate_input_file(candidate_file)
        except nuancierlib.NuancierException as err:
            app.log.debug('ERROR: Uploaded file is invalid - user: "%s" '
                          'election: "%s"', flask.g.fas_user.username,
                          election_id)
            app.log.exception(err)
            flask.flash(err.message, 'error')
            return flask.render_template(
                'contribute.html',
                election=election,
                form=form)

        filename = secure_filename('%s-%s' % (flask.g.fas_user.username,
                                   candidate_file.filename))

        # Only save the file once everything has been safely saved in the DB
        upload_folder = os.path.join(
            app.config['PICTURE_FOLDER'], election.election_folder)
        if not os.path.exists(upload_folder):  # pragma: no cover
            try:
                os.mkdir(upload_folder)
            except OSError, err:
                app.log.debug('ERROR: cannot add candidate file')
                app.log.exception(err)
                flask.flash(
                    'An error occured while writing the file, please '
                    'contact an administrator', 'error')
                return flask.render_template(
                    'contribute.html',
                    election=election,
                    form=form)

        # Save candidate to the database
        try:
            nuancierlib.add_candidate(
                app.db_session,
                candidate_file=filename,
                candidate_name=form.candidate_name.data,
                candidate_author=form.candidate_author.data,
                candidate_original_url=form.candidate_original_url.data,
                candidate_license=form.candidate_license.data,
                candidate_submitter=flask.g.fas_user.username,
                submitter_email=flask.g.fas_user.email,
                election_id=election.id,
                user=flask.g.fas_user.username,
            )
        except nuancierlib.NuancierException as err:
            flask.flash(err.message, 'error')
            return flask.render_template(
                'contribute.html',
                election=election,
                form=form)

        # The PIL module has already read the stream so we need to back up
        candidate_file.seek(0)

        candidate_file.save(
            os.path.join(upload_folder, filename))

        try:
            app.db_session.commit()
        except SQLAlchemyError as err:  # pragma: no cover
            app.db_session.rollback()
            # Remove file from the system if the db commit failed
            os.unlink(os.path.join(upload_folder, filename))
            app.log.debug('ERROR: cannot add candidate - user: "%s" '
                          'election: "%s"', flask.g.fas_user.username,
                          election_id)
            app.log.exception(err)
            flask.flash(
                'Someone has already upload a file with the same file name'
                ' for this election', 'error')
            return flask.render_template(
                'contribute.html',
                election=election,
                form=form)

        flask.flash('Thanks for your submission')
        return flask.redirect(flask.url_for('index'))
    elif flask.request.method == 'GET':
        form.candidate_author.data = flask.g.fas_user.username

    return flask.render_template(
        'contribute.html',
        election=election,
        form=form)


@app.route('/elections/')
def elections_list():
    ''' Displays the results of all published election. '''
    elections = nuancierlib.get_elections(app.db_session)

    return flask.render_template(
        'elections_list.html',
        elections=elections)


@app.route('/election/<int:election_id>/')
def election(election_id):
    ''' Display the index page of the election will all the candidates
    submitted. '''
    election = nuancierlib.get_election(app.db_session, election_id)
    if not election:
        flask.flash('No election found', 'error')
        return flask.render_template('msg.html')

    # How many votes the user made:
    votes = []
    can_vote = True
    if hasattr(flask.g, 'fas_user') and flask.g.fas_user:
        votes = nuancierlib.get_votes_user(app.db_session, election_id,
                                           flask.g.fas_user.username)

    if election.election_open and len(votes) < election.election_n_choice:
        if len(votes) > 0:
            flask.flash('You have already voted, but you can still vote '
                        'on more candidates.')
        return flask.redirect(flask.url_for('vote', election_id=election_id))
    elif election.election_open and len(votes) >= election.election_n_choice:
        can_vote = False
    elif not election.election_public:
        flask.flash('This election is not open', 'error')
        return flask.redirect(flask.url_for('elections_list'))

    candidates = nuancierlib.get_candidates(
        app.db_session, election_id, approved=True)

    if hasattr(flask.g, 'fas_user') and flask.g.fas_user:
        random.seed(
            int(
                hashlib.sha1(flask.g.fas_user.username).hexdigest(), 16
            ) % 100000)
    random.shuffle(candidates)

    return flask.render_template(
        'election.html',
        candidates=candidates,
        election=election,
        can_vote=can_vote,
        picture_folder=os.path.join(
            app.config['PICTURE_FOLDER'], election.election_folder),
        cache_folder=os.path.join(
            app.config['CACHE_FOLDER'], election.election_folder)
    )


@app.route('/election/<int:election_id>/vote/')
@contributor_required
def vote(election_id):
    ''' Give the possibility to the user to vote for an election. '''
    election = nuancierlib.get_election(app.db_session, election_id)
    if not election:
        flask.flash('No election found', 'error')
        return flask.render_template('msg.html')
    candidates = nuancierlib.get_candidates(
        app.db_session, election_id, approved=True)

    if not election.election_open:
        flask.flash('This election is not open', 'error')
        return flask.redirect(flask.url_for('index'))

    if flask.g.fas_user:
        random.seed(
            int(
                hashlib.sha1(flask.g.fas_user.username).hexdigest(), 16
            ) % 100000)
    random.shuffle(candidates)

    # How many votes the user made:
    votes = nuancierlib.get_votes_user(app.db_session, election_id,
                                       flask.g.fas_user.username)

    if len(votes) >= election.election_n_choice:
        flask.flash('You have cast the maximal number of votes '
                    'allowed for this election.', 'error')
        return flask.redirect(
            flask.url_for('election', election_id=election_id))

    if len(votes) > 0:
        candidate_done = [cdt.candidate_id for cdt in votes]
        candidates = [candidate
                      for candidate in candidates
                      if candidate.id not in candidate_done]

    return flask.render_template(
        'vote.html',
        election=election,
        form=forms.ConfirmationForm(),
        candidates=candidates,
        n_votes_done=len(votes),
        picture_folder=os.path.join(
            app.config['PICTURE_FOLDER'], election.election_folder),
        cache_folder=os.path.join(
            app.config['CACHE_FOLDER'], election.election_folder)
    )


@app.route('/election/<int:election_id>/voted/', methods=['POST'])
@contributor_required
def process_vote(election_id):
    ''' Actually register the vote, after checking if the user is actually
    allowed to vote.
    '''

    form = forms.ConfirmationForm()
    if not form.validate_on_submit():
        flask.flash('Wrong input submitted', 'error')
        return flask.render_template('msg.html')

    election = nuancierlib.get_election(app.db_session, election_id)
    if not election:
        flask.flash('No election found', 'error')
        return flask.render_template('msg.html')

    if not election.election_open:
        flask.flash('This election is not open', 'error')
        return flask.render_template('msg.html')

    candidates = nuancierlib.get_candidates(
        app.db_session, election_id, approved=True)
    candidate_ids = set([candidate.id for candidate in candidates])

    entries = set([int(entry)
                   for entry in flask.request.form.getlist('selection')])

    # If not enough candidates selected
    if not entries:
        flask.flash('You did not select any candidate to vote for.', 'error')
        return flask.redirect(flask.url_for('vote', election_id=election_id))

    # If vote on candidates from other elections
    if not set(entries).issubset(candidate_ids):
        flask.flash('The selection you have made contains element which are '
                    'not part of this election, please be careful.', 'error')
        return flask.redirect(flask.url_for('vote', election_id=election_id))

    # How many votes the user made:
    votes = nuancierlib.get_votes_user(app.db_session, election_id,
                                       flask.g.fas_user.username)

    # Too many votes -> redirect
    if len(votes) >= election.election_n_choice:
        flask.flash('You have cast the maximal number of votes '
                    'allowed for this election.', 'error')
        return flask.redirect(
            flask.url_for('election', election_id=election_id))

    # Selected more candidates than allowed -> redirect
    if len(votes) + len(entries) > election.election_n_choice:
        flask.flash('You selected %s wallpapers while you are only allowed '
                    'to select %s' % (
                        len(entries),
                        (election.election_n_choice - len(votes))),
                    'error')
        return flask.render_template(
            'vote.html',
            form=forms.ConfirmationForm(),
            election=election,
            candidates=[nuancierlib.get_candidate(app.db_session, candidate_id)
                        for candidate_id in entries],
            n_votes_done=len(votes),
            picture_folder=os.path.join(
                app.config['PICTURE_FOLDER'], election.election_folder),
            cache_folder=os.path.join(
                app.config['CACHE_FOLDER'], election.election_folder)
        )

    # Allowed to vote, selection sufficient, choice confirmed: process
    for selection in entries:
        value = 1
        if has_weigthed_vote(flask.g.fas_user):
            value = 2
        nuancierlib.add_vote(
            app.db_session, selection, flask.g.fas_user.username, value=value)

    try:
        app.db_session.commit()
    except SQLAlchemyError as err:  # pragma: no cover
        app.db_session.rollback()
        app.log.debug('ERROR: could not process the vote - user: "%s" '
                      'election: "%s"', flask.g.fas_user.username,
                      election_id)
        app.log.exception(err)
        flask.flash('An error occured while processing your votes, please '
                    'report this to your lovely admin or see logs for '
                    'more details', 'error')

    flask.flash('Your vote has been recorded, thank you for voting on '
                '%s %s' % (election.election_name, election.election_year))

    if election.election_badge_link:
        flask.flash('Do not forget to <a href="%s" target="_blank">claim your '
                    'badge!</a>' % election.election_badge_link)
    return flask.redirect(flask.url_for('elections_list'))


@app.route('/results/')
def results_list():
    ''' Displays the results of all published election. '''
    elections = nuancierlib.get_elections_public(app.db_session)

    return flask.render_template(
        'result_list.html',
        elections=elections)


@app.route('/results/<int:election_id>/')
def results(election_id):
    ''' Displays the results of an election. '''
    election = nuancierlib.get_election(app.db_session, election_id)

    if not election:
        flask.flash('No election found', 'error')
        return flask.render_template('msg.html')

    if not election.election_public:
        flask.flash('The results this election are not public yet', 'error')
        return flask.redirect(flask.url_for('results_list'))

    election_results = nuancierlib.get_results(app.db_session, election_id)

    return flask.render_template(
        'results.html',
        election=election,
        results=election_results,
        picture_folder=os.path.join(
            app.config['PICTURE_FOLDER'], election.election_folder),
        cache_folder=os.path.join(
            app.config['CACHE_FOLDER'], election.election_folder))


@app.route('/stats/<int:election_id>/')
def stats(election_id):
    ''' Return some stats about this election. '''
    election = nuancierlib.get_election(app.db_session, election_id)

    if not election:
        flask.flash('No election found', 'error')
        return flask.render_template('msg.html')

    if not election.election_public:
        flask.flash('The results this election are not public yet', 'error')
        return flask.redirect(flask.url_for('results_list'))

    statsinfo = nuancierlib.get_stats(app.db_session, election_id)

    return flask.render_template(
        'stats.html',
        stats=statsinfo,
        election=election)


@app.route('/contributions/')
@fas_login_required
def contributions():
    ''' Display the contributions denied made by the user logged in. '''
    contributions = nuancierlib.get_contributions(
        app.db_session, flask.g.fas_user.username)

    return flask.render_template(
        'contributions.html',
        contributions=contributions)


@app.route('/contribution/<cand_id>/update', methods=['GET', 'POST'])
@fas_login_required
def update_candidate(cand_id):
    ''' Display the index page for interested contributor. '''
    candidate = nuancierlib.get_candidate(app.db_session, cand_id)

    # First some security checks
    if not candidate:
        flask.flash('No candidate found', 'error')
        return flask.render_template('msg.html')
    elif not candidate.election.submission_open:
        flask.flash(
            'The election of this candidate is not open for submission',
            'error')
        return flask.redirect(flask.url_for('elections_list'))
    elif candidate.approved:
        flask.flash(
            'This candidate was already approved, you cannot update it',
            'error')
        return flask.redirect(flask.url_for('elections_list'))
    elif candidate.candidate_submitter != flask.g.fas_user.username:
        flask.flash(
            'You are not the person that submitted this candidate, you may '
            'not update it', 'error')
        return flask.redirect(flask.url_for('elections_list'))

    form = forms.AddCandidateForm(obj=candidate)
    if form.validate_on_submit():
        candidate_file = flask.request.files['candidate_file']

        try:
            _validate_input_file(candidate_file)
        except nuancierlib.NuancierException as err:
            app.log.debug('ERROR: Uploaded file is invalid - user: "%s" '
                          'election: "%s"', flask.g.fas_user.username,
                          candidate.election.id)
            app.log.exception(err)
            flask.flash(err.message, 'error')
            return flask.render_template(
                'update_contribution.html',
                candidate=candidate,
                form=form)

        filename = secure_filename('%s-%s' % (flask.g.fas_user.username,
                                   candidate_file.filename))

        # Only save the file once everything has been safely saved in the DB
        upload_folder = os.path.join(
            app.config['PICTURE_FOLDER'],
            candidate.election.election_folder)
        if not os.path.exists(upload_folder):  # pragma: no cover
            try:
                os.mkdir(upload_folder)
            except OSError, err:
                app.log.debug('ERROR: cannot add candidate file')
                app.log.exception(err)
                flask.flash(
                    'An error occured while writing the file, please '
                    'contact an administrator', 'error')
                return flask.render_template(
                    'update_contribution.html',
                    candidate=candidate,
                    form=form)

        # Update the candidate
        form.populate_obj(obj=candidate)
        candidate.candidate_file = filename
        candidate.approved = False
        candidate.approved_motif = None
        app.db_session.add(candidate)

        # The PIL module has already read the stream so we need to back up
        candidate_file.seek(0)
        candidate_file.save(
            os.path.join(upload_folder, filename))

        try:
            app.db_session.commit()
        except SQLAlchemyError as err:  # pragma: no cover
            app.log.debug(err)
            app.db_session.rollback()
            # Remove file from the system if the db commit failed
            os.unlink(os.path.join(upload_folder, filename))
            app.log.debug('ERROR: cannot add candidate - user: "%s" '
                          'election: "%s"', flask.g.fas_user.username,
                          candidate.election.id)
            app.log.exception(err)
            flask.flash(
                'Someone has already upload a file with the same file name'
                ' for this election', 'error')
            return flask.render_template(
                'update_contribution.html',
                candidate=candidate,
                form=form)

        flask.flash('Thanks for updating your submission')
        return flask.redirect(flask.url_for('index'))

    return flask.render_template(
        'update_contribution.html',
        candidate=candidate,
        form=form)


@app.cache.cache_on_arguments(expiration_time=3600)
@app.route('/pictures/<path:filename>')
def base_picture(filename):
    ''' Returns a picture having the provided path relative to the
    PICTURE_FOLDER set in the configuration.
    '''
    return flask.send_from_directory(app.config['PICTURE_FOLDER'], filename)


@app.cache.cache_on_arguments(expiration_time=3600)
@app.route('/cache/<path:filename>')
def base_cache(filename):
    ''' Returns a picture having the provided path relative to the
    CACHE_FOLDER set in the configuration.
    '''
    return flask.send_from_directory(app.config['CACHE_FOLDER'], filename)


@app.route('/msg/')
def msg():
    ''' Page used to display error messages
    '''
    return flask.render_template('msg.html')


@app.route('/login/', methods=['GET', 'POST'])
def login():  # pragma: no cover
    ''' Login mechanism for this application.
    '''
    next_url = None
    if 'next' in flask.request.args:
        if _is_safe_url(flask.request.args['next']):
            next_url = flask.request.args['next']

    if not next_url or next_url == flask.url_for('.login'):
        next_url = flask.url_for('.index')

    if hasattr(flask.g, 'fas_user') and flask.g.fas_user is not None:
        return flask.redirect(next_url)
    else:
        admins = app.config['ADMIN_GROUP']
        if isinstance(admins, basestring):  # pragma: no cover
            admins = set([admins])
        else:
            admins = set(admins)

        groups = list(admins)[:]

        reviewers = app.config['REVIEW_GROUP']
        if isinstance(reviewers, basestring):  # pragma: no cover
            reviewers = set([reviewers])
        else:
            reviewers = set(reviewers)

        groups.extend(reviewers)

        voters = app.config['WEIGHTED_GROUP']
        if isinstance(voters, basestring):  # pragma: no cover
            voters = set([voters])
        else:
            voters = set(voters)

        groups.extend(voters)

        return app.fas.login(return_url=next_url, groups=groups)


@app.route('/logout/')
def logout():  # pragma: no cover
    ''' Log out if the user is logged in other do nothing.
    Return to the index page at the end.
    '''
    next_url = None
    if 'next' in flask.request.args:
        if _is_safe_url(flask.request.args['next']):
            next_url = flask.request.args['next']

    if not next_url or next_url == flask.url_for('.login'):
        next_url = flask.url_for('.index')

    if hasattr(flask.g, 'fas_user') and flask.g.fas_user is not None:
        app.fas.logout()
        flask.flash('You are no longer logged-in')

    return flask.redirect(next_url)
