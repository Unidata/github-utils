#!/usr/bin/env python
from __future__ import print_function
from datetime import datetime, timedelta
from functools import lru_cache
from operator import itemgetter
import github


# PyGitHub doesn't yet support the new watchers->subscribers API, so we borrow
# some of their method code
def get_subscribers(self):
    """
    :calls: `GET /repos/:owner/:repo/watchers <http://developer.github.com/v3/activity/starring>`_
    :rtype: :class:`github.PaginatedList.PaginatedList` of :class:`github.NamedUser.NamedUser`
    """
    return github.PaginatedList.PaginatedList(
        github.NamedUser.NamedUser,
        self._requester,
        self.url + "/subscribers",
        None
    )


class Contributor(tuple):
    _known_users = None
    login = property(itemgetter(0))
    name = property(itemgetter(1))
    email = property(itemgetter(2))
    affiliation = property(itemgetter(3))
    type = property(itemgetter(4))

    def __new__(cls, login, name, email, company):
        affil, typ = Contributor._lookup_user(login, email, company)
        return super(Contributor, cls).__new__(cls, (login, name if name else 'Unknown',
                                                     email if email else 'Unknown', affil,
                                                     typ))

    @classmethod
    def _lookup_user(cls, login, email, company):
        if cls._known_users is None:
            cls._init_cache()

        affil, typ = None, None
        if login in cls._known_users:
            return cls._known_users[login]

        if company:
            affil = company
            affil_test = affil.lower()
            if 'university' in affil_test or 'univ.' in affil_test or 'UCAR' in affil:
                typ = 'EDU'
            elif ('NOAA' in affil or 'NWS' in affil or 'NASA' in affil or
                  'national lab' in affil_test):
                typ = 'GOV'

        if email and (email.endswith('edu') or email.endswith('gov') or
                      email.endswith('mil')):
            if not affil:
                affil = email.split('@')[-1].rsplit('.', 1)[0].title()
            if not typ:
                typ = email.rsplit('.', 1)[-1].upper()
        return affil if affil else 'Unknown', typ if typ else 'Unknown'

    @classmethod
    def _init_cache(cls):
        cls._known_users = dict()
        try:
            with open('known_users', 'rt') as userfile:
                for line in userfile:
                    login, affil, typ = line.rstrip().split(',')
                    cls._known_users[login] = affil.strip(), typ.strip()
        except IOError:
            pass

    def __str__(self):
        return u', '.join(self)


def filter_members(users, members):
    return set(users) - members


def get_user(item):
    try:
        user = item.user
    except AttributeError:
        user = item

    if user.login not in get_user.cache:
        get_user.cache[user.login] = Contributor(user.login, user.name, user.email,
                                                 user.company)

    return get_user.cache[user.login]

get_user.cache = dict()


def get_external_participation(issues, members, start):
    opened = dict()
    comments = dict()
    for i in issues:
        user = get_user(i)
        if user not in members and i.created_at >= start:
            opened.setdefault(user, []).append(i)
        for c in i.get_comments():
            user = get_user(c)
            if user not in members and c.created_at >= start:
                comments.setdefault(user, []).append(c)
    return opened, comments


def get_support_effort(ext_issues):
    return sum(i.comments for issues in ext_issues.values() for i in issues)


def get_token():
    r"""
    Get the API token to use for talking to GitHub
    """
    try:
        with open('token', 'rt') as token_file:
            return token_file.readline()[:-1]
    except IOError:
        import os
        return os.environ.get('GITHUB_TOKEN')


def created_count(issues, start):
    return count_if(issues, lambda i: i.created_at >= start)


def closed_count(issues, start):
    return count_if(issues, lambda i: i.state == 'closed' and i.closed_at >= start)


def count_if(seq, pred):
    return sum(1 for item in seq if pred(item))


# useful for generators without making the full list
def count(seq):
    return sum(1 for _ in seq)


def print_users(users):
    # Format for printing users
    for u in users:
        print(u'\t\t' + str(u))


def count_total_items(dict_of_list):
    return sum(len(item) for item in dict_of_list.values())


class RepoMetrics(object):
    def __init__(self, repo, start, blacklist):
        self._repo = repo
        self._start = start
        self._blacklist = blacklist
        self._prs = self._issues = None

    @property
    @lru_cache()
    def prs(self):
        self._fetch_issues()
        return self._prs

    @property
    @lru_cache()
    def issues(self):
        self._fetch_issues()
        return self._issues

    @property
    @lru_cache()
    def ext_issues(self):
        self._fetch_external_issues()
        return self._ext_issues

    @property
    @lru_cache()
    def ext_issue_comments(self):
        self._fetch_external_issues()
        return self._ext_issue_comments

    @property
    @lru_cache()
    def ext_prs(self):
        self._fetch_external_prs()
        return self._ext_prs

    @property
    @lru_cache()
    def ext_pr_comments(self):
        self._fetch_external_prs()
        return self._ext_pr_comments

    @property
    def contributors(self):
        return (set(self.ext_issues) | set(self.ext_issue_comments) |
                set(self.ext_prs) | set(self.ext_pr_comments))

    @property
    def name(self):
        return self._repo.name

    @property
    def total_stars(self):
        return (s for s in self._fetch_stars() if get_user(s) not in self._blacklist)

    @property
    def new_stars(self):
        return (s for s in self.total_stars if s.starred_at > self._start)

    @property
    def watchers(self):
        return (w for w in self._fetch_watchers() if get_user(w) not in self._blacklist)

    @property
    def total_forks(self):
        return (f.owner for f in self._fetch_forks()
                if get_user(f.owner) not in self._blacklist)

    @property
    def new_forks(self):
        return (f for f in self.total_forks if f.created_at > self._start)

    @property
    @lru_cache()
    def commits(self):
        return self._repo.get_commits(since=self._start)

    @property
    def events(self):
        for user, user_issues in self.ext_issues.items():
            for i in user_issues:
                yield (i.created_at, 'Issue', user)
        for user, user_comments in self.ext_issue_comments.items():
            for c in user_comments:
                yield (c.created_at, 'Comment', user)
        for user, user_issues in self.ext_prs.items():
            for i in user_issues:
                yield (i.created_at, 'PR', user)
        for user, user_comments in self.ext_pr_comments.items():
            for c in user_comments:
                yield (c.created_at, 'PR Comment', user)
        for star in self.new_stars:
            yield (star.starred_at, 'Star', get_user(star.user))

    @lru_cache()
    def _fetch_forks(self):
        return self._repo.get_forks()

    def _fetch_issues(self):
        """
        Get issues and pull requests since a given time
        """
        # Filter results to issues and PRs
        self._issues = []
        self._prs = []
        for i in self._repo.get_issues(state='all', since=self._start):
            if i.pull_request:
                self._prs.append(i)
            else:
                self._issues.append(i)

    @lru_cache()
    def _fetch_watchers(self):
        return get_subscribers(self._repo)

    @lru_cache()
    def _fetch_stars(self):
        return self._repo.get_stargazers_with_dates()

    def _fetch_external_issues(self):
        self._ext_issues, self._ext_issue_comments = get_external_participation(self.issues,
                                                                                self._blacklist,
                                                                                self._start)

    def _fetch_external_prs(self):
        self._ext_prs, self._ext_pr_comments = get_external_participation(self.issues,
                                                                          self._blacklist,
                                                                          self._start)


def output_default(metrics, verbose=0):
    print('Repository: {0}'.format(metrics.name))
    print('\tActive Issues: {0} ({1} created, {2} closed)'.format(
        len(metrics.issues), created_count(metrics.issues, start),
        closed_count(metrics.issues, start)))
    print('\tActive PRs: {0} ({1} created, {2} closed)'.format(
        len(metrics.prs), created_count(metrics.prs, start),
        closed_count(metrics.prs, start)))
    print('\tExternal Issue Activity: {0} opened, {1} comments'.format(
        count_total_items(metrics.ext_issues),
        count_total_items(metrics.ext_issue_comments)))
    print('\t\tTotal replies for created issues: {0}'.format(
        get_support_effort(metrics.ext_issues)))
    print('\tExternal PR Activity: {0} opened, {1} comments'.format(
        count_total_items(metrics.ext_prs), count_total_items(metrics.ext_pr_comments)))
    print('\t\tTotal replies for created PRs: {0}'.format(get_support_effort(metrics.ext_prs)))
    print('\tUnique external contributors: {0}'.format(len(metrics.contributors)))

    if verbose:
        print_users(metrics.contributors)

    print('\tStars: {0} ({1} total)'.format(count(metrics.new_stars),
                                            count(metrics.total_stars)))
    if verbose:
        print_users(get_user(s) for s in metrics.new_stars)

    print('\tWatchers: {0}'.format(count(metrics.watchers)))
    if verbose:
        print_users(get_user(w) for w in metrics.watchers)

    print('\tForks: {0} ({1} total)'.format(count(metrics.new_forks),
                                            count(metrics.total_forks)))
    if verbose:
        print_users(get_user(f) for f in metrics.new_forks)

    print('\tCommits: {0}'.format(count(metrics.commits)))

    if verbose >= 2:
        print('\tActivity Listing:')
        for dt, kind, user in sorted(metrics.events):
            print(u'\t\t{0}, {1}, {2}'.format(dt, kind, user))


if __name__ == '__main__':
    import argparse

    # Get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('repository', help='Repository', type=str, nargs='*',
                        default=['siphon', 'MetPy', 'thredds', 'netcdf-c',
                                 'netcdf-cxx4', 'netcdf-fortran',
                                 'netCDF-Decoders', 'netCDF-Perl', 'idv',
                                 'LDM', 'awips2', 'gempak', 'rosetta',
                                 'UDUNITS-2', 'unidata-python-workshop'])
    parser.add_argument('-o', '--org', help='Organization', type=str, default='Unidata')
    parser.add_argument('-s', '--start', help='Starting date for stats [YYYYMMDD]', type=str)
    parser.add_argument('-d', '--days', help='Get stats for last n days', type=int,
                        default=90)
    parser.add_argument('-v', '--verbose', help='Verbose output', action='count',
                        default=0)
    parser.add_argument('--debug', help='Print out debugging information', action='store_true')
    args = parser.parse_args()

    if args.start:
        start = datetime.strptime(args.start, '%Y%m%d')
    else:
        start = datetime.utcnow() - timedelta(days=args.days)

    # Get the github API entry
    g = github.Github(get_token())

    if args.debug:
        rate = g.get_rate_limit().rate
        print('API calls remaining: {0} (Resets at {1})'.format(rate.remaining, rate.reset))

    # Get the organization
    org = g.get_organization(args.org)

    # Get blacklist of internal members so we can exclude from some stats
    blacklist = {get_user(m) for m in org.get_members()}

    # Add other users to blacklist
    other_users = ['codecov-io', 'landscape-bot', 'rkambic', 'madry',
                   'BenDomenico']
    blacklist |= {get_user(g.get_user(u)) for u in other_users}

    # Release downloads?

    print('Stats for {0} since {1}'.format(args.org, start))
    for repo_name in args.repository:
        # Get the object for this repository
        repo = org.get_repo(repo_name)
        output_default(RepoMetrics(repo, start, blacklist), args.verbose)
