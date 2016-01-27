#!/usr/bin/env python
from __future__ import print_function
from datetime import datetime, timedelta
from collections import Counter
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
            if 'university' in affil_test or 'UCAR' in affil:
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


def filter_members(users, members):
    return set(users) - members


def get_stars(repo, since, members):
    stars = repo.get_stargazers_with_dates()
    total_stars = [s for s in stars if get_user(s) not in blacklist]
    new_stars = [s for s in stars if s.starred_at > start and get_user(s) not in blacklist]
    return new_stars, total_stars


def get_activity(repo, since):
    r"""
    Get issues and pull requests since a given time
    """
    issues = repo.get_issues(state='all', since=since)

    # Filter results to issues and PRs
    real_issues = []
    prs = []
    for i in issues:
        if i.pull_request:
            prs.append(i)
        else:
            real_issues.append(i)

    return real_issues, prs


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

def get_external_participation(issues, members):
    opened = Counter()
    comments = Counter()
    for i in issues:
        user = get_user(i)
        if user not in members:
            opened[user] += 1
        for c in i.get_comments():
            user = get_user(c)
            if user not in members:
                comments[user] += 1
    return opened, comments


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


def closed_count(issues):
    return len(list(filter(is_closed, issues)))


def is_closed(issue):
    return issue.state == 'closed'


def print_users(users):
    # Format for printing users
    fmt = u'\t\t{0}, {1}, {2}, {3}, {4}'
    print(fmt.format('User', 'Name', 'Email', 'Affiliation', 'Type'))
    for u in users:
        print(fmt.format(u.login, u.name, u.email, u.affiliation, u.type))


if __name__ == '__main__':
    import argparse

    # Get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('repository', help='Repository', type=str, nargs='*',
                        default=['siphon', 'thredds', 'netcdf-c', 'idv', 'LDM', 'awips2',
                                 'gempak', 'rosetta', 'UDUNITS-2'])
    parser.add_argument('-o', '--org', help='Organization', type=str, default='Unidata')
    parser.add_argument('-s', '--start', help='Starting date for stats [YYYYMMDD]', type=str)
    parser.add_argument('-d', '--days', help='Get stats for last n days', type=int,
                        default=90)
    parser.add_argument('-v', '--verbose', help='Verbose output', action='count')
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
    other_users = ['codecov-io', 'landscape-bot', 'rkambic', 'madry']
    blacklist |= {get_user(g.get_user(u)) for u in other_users}

    # Commits?
    # Release downloads?

    print('Stats for {0} since {1}'.format(args.org, start))
    for repo_name in args.repository:
        # Get the object for this repository
        repo = org.get_repo(repo_name)
        print('Repository: {0}'.format(repo.name))

        # Get separate lists for issues and PRs
        issues, prs = get_activity(repo, start)
        print('\tIssues: {0} ({1} closed)'.format(len(issues), closed_count(issues)))
        print('\tPRs: {0} ({1} closed)'.format(len(prs), closed_count(prs)))

        # Get those opened/commented upon by non-members
        ext_issues, ext_issue_comments = get_external_participation(issues, blacklist)
        ext_prs, ext_pr_comments = get_external_participation(prs, blacklist)
        print('\tExternal Issues: {0} opened, {1} comments'.format(
                sum(ext_issues.values()), sum(ext_issue_comments.values())))
        print('\tExternal PRs: {0} opened, {1} comments'.format(
                sum(ext_prs.values()), sum(ext_pr_comments.values())))

        # Gather up all of those users
        contributors = (set(ext_issues.keys()) | set(ext_issue_comments.keys()) |
                        set(ext_prs.keys()) | set(ext_pr_comments.keys()))
        print('\tUnique external contributors: {0}'.format(len(contributors)))
        if args.verbose:
            print_users(contributors)

        # Get total stars and stars added since start
        new_stars, total_stars = get_stars(repo, start, blacklist)
        print('\tStars: {0} ({1} total)'.format(len(new_stars), len(total_stars)))
        if args.verbose:
            print_users(get_user(s) for s in new_stars)

        # Also grab users who are watching repo activity
        watchers = [w for w in get_subscribers(repo) if get_user(w) not in blacklist]
        watch_count = sum(1 for w in watchers)
        print('\tWatchers: {0}'.format(watch_count))
        if args.verbose:
            print_users(get_user(w) for w in watchers)

        # Get all of the commits since the start of the period
        commit_count = sum(1 for c in repo.get_commits(since=start))
        print('\tCommits: {0}'.format(commit_count))
