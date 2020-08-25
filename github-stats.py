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

    affil_keys = [('EDU', ('university', 'univ.', 'ucar', 'ncar',
                           'national center for atmospheric', 'comet')),
                  ('GOV', ('noaa', 'nws', 'nasa', 'national lab'))]

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
            for category, keys in cls.affil_keys:
                for key in keys:
                    if key in affil_test:
                        typ = category
                        break
                if typ:
                    break

        if email and email.endswith(('edu', 'gov', 'mil')):
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


def get_external_participation(issues, members, date_check):
    opened = dict()
    comments = dict()
    for i in issues:
        user = get_user(i)
        if user not in members and date_check(i.created_at):
            opened.setdefault(user, []).append(i)
        for c in i.get_comments():
            user = get_user(c)
            if user not in members and date_check(c.created_at):
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


def created_count(issues, date_check):
    return count_if(issues, lambda i: date_check(i.created_at))


def closed_count(issues, date_check):
    return count_if(issues, lambda i: i.state == 'closed' and date_check(i.closed_at))


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


def count_total_closed(dict_of_list, date_check):
    return sum(closed_count(issues, date_check) for issues in dict_of_list.values())


class RepoMetrics(object):
    def __init__(self, repo, start, end, blacklist):
        self._repo = repo
        self._start = start
        self._end = end
        self._blacklist = blacklist
        self._prs = self._issues = None
        self.date_in_range = lambda d: self._start <= d <= self._end

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
        return (s for s in self.total_stars if self.date_in_range(s.starred_at))

    @property
    def watchers(self):
        return (w for w in self._fetch_watchers() if get_user(w) not in self._blacklist)

    @property
    def total_forks(self):
        return (f.owner for f in self._fetch_forks()
                if get_user(f.owner) not in self._blacklist)

    @property
    def new_forks(self):
        return (f for f in self.total_forks if self.date_in_range(f.created_at))

    @property
    @lru_cache()
    def commits(self):
        return self._repo.get_commits(since=self._start, until=self._end)

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
            if (self.date_in_range(i.created_at) or self.date_in_range(i.updated_at) or
                    (i.state == 'closed' and self.date_in_range(i.closed_at))):
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
        self._ext_issues, self._ext_issue_comments = get_external_participation(
            self.issues, self._blacklist, self.date_in_range)

    def _fetch_external_prs(self):
        self._ext_prs, self._ext_pr_comments = get_external_participation(
            self.prs, self._blacklist, self.date_in_range)


def output_default(metrics, verbose=0):
    print('Repository: {0}'.format(metrics.name))

    print('\tWatchers: {0}'.format(count(metrics.watchers)))
    if verbose:
        print_users(get_user(w) for w in metrics.watchers)

    print('\tActive Issues: {0} ({1} created, {2} closed)'.format(
        len(metrics.issues), created_count(metrics.issues, metrics.date_in_range),
        closed_count(metrics.issues, metrics.date_in_range)))
    print('\tActive PRs: {0} ({1} created, {2} closed)'.format(
        len(metrics.prs), created_count(metrics.prs, metrics.date_in_range),
        closed_count(metrics.prs, metrics.date_in_range)))
    print('\tExternal Issue Activity: {0} opened, {1} comments'.format(
        count_total_items(metrics.ext_issues),
        count_total_items(metrics.ext_issue_comments)))
    if verbose:
        print('\t\tTotal replies for created issues: {0}'.format(
            get_support_effort(metrics.ext_issues)))
    print('\tExternal PR Activity: {0} opened, {1} comments'.format(
        count_total_items(metrics.ext_prs), count_total_items(metrics.ext_pr_comments)))
    if verbose:
        print('\t\tTotal replies for created PRs: {0}'.format(get_support_effort(metrics.ext_prs)))
    print('\tUnique external contributors: {0}'.format(len(metrics.contributors)))

    print('\tStars: {0} ({1} total)'.format(count(metrics.new_stars),
                                            count(metrics.total_stars)))
    if verbose:
        print_users(get_user(s) for s in metrics.new_stars)

    print('\tForks: {0} ({1} total)'.format(count(metrics.new_forks),
                                            count(metrics.total_forks)))
    if verbose:
        print_users(get_user(f) for f in metrics.new_forks)

    print('\tCommits: {0}'.format(count(metrics.commits)))

    print_users(metrics.contributors)

    if verbose >= 2:
        print('\tActivity Listing:')
        for dt, kind, user in sorted(metrics.events):
            print(u'\t\t{0}, {1}, {2}'.format(dt, kind, user))


def nsf_output(metrics, *args):
    print('Repository: {0}'.format(metrics.name))
    print('\tExternal Issue Activity:\n\t\t{0} opened\n\t\t{1} closed\n\t\t{2} comments'.format(
        count_total_items(metrics.ext_issues),
        count_total_closed(metrics.ext_issues, metrics.date_in_range),
        count_total_items(metrics.ext_issue_comments)))
    print('\tExternal PR Activity:\n\t\t{0} opened\n\t\t{1} closed\n\t\t{2} comments'.format(
        count_total_items(metrics.ext_prs),
        count_total_closed(metrics.ext_prs, metrics.date_in_range),
        count_total_items(metrics.ext_pr_comments)))

    print('\tUnique external contributors: {0}'.format(len(metrics.contributors)))
    print_users(metrics.contributors)

    print('\tStars: {0} ({1} total)'.format(count(metrics.new_stars),
                                            count(metrics.total_stars)))
    print_users(get_user(s) for s in metrics.new_stars)

    print('\tWatchers: {0}'.format(count(metrics.watchers)))
    print_users(get_user(w) for w in metrics.watchers)

    print('\tForks: {0} ({1} total)'.format(count(metrics.new_forks),
                                            count(metrics.total_forks)))
    print_users(get_user(f) for f in metrics.new_forks)


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
    parser.add_argument('-f', '--format', help='Output format', type=str, default='default')
    parser.add_argument('-o', '--org', help='Organization', type=str, default='Unidata')
    parser.add_argument('-s', '--start', help='Starting date for stats [YYYYMMDD]', type=str)
    parser.add_argument('-e', '--end', help='Ending date for stats [YYYYMMDD]', type=str)
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

    if args.end:
        end = datetime.strptime(args.end, '%Y%m%d')
    else:
        end = datetime.utcnow()

    formats = dict(default=output_default, nsf=nsf_output)
    formatter = formats.get(args.format, output_default)

    # Get the github API entry
    g = github.Github(get_token())

    if args.debug:
        rate = g.get_rate_limit().core
        print('API calls remaining: {0} (Resets at {1})'.format(rate.remaining, rate.reset))

    # Get the organization
    org = g.get_organization(args.org)

    # Get blacklist of internal members so we can exclude from some stats
    blacklist = {get_user(m) for m in org.get_members()}

    # Add other users to blacklist
    other_users = ['codecov-io', 'landscape-bot', 'rkambic', 'madry', 'BenDomenico',
                   'JohnLCaron', 'russrew', 'donmurray', 'lago8103', 'mwilson14', 'tjwixtrom',
                   'CLAassistant', 'codecov[bot]', 'haileyajohnson', 'mgrover1',
                   'stickler-ci', 'jrleeman', 'zbruick', 'dependabot[bot]']
    blacklist |= {get_user(g.get_user(u)) for u in other_users}

    # Release downloads?

    print('Stats for {0} from {1} to {2}'.format(args.org, start, end))
    for repo_name in args.repository:
        # Get the object for this repository
        repo = org.get_repo(repo_name)
        formatter(RepoMetrics(repo, start, end, blacklist), args.verbose)
