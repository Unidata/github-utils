#!/usr/bin/env python
from __future__ import print_function
from datetime import datetime, timedelta
from collections import Counter
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


def filter_members(users, members):
    return {u.login for u in users} - members


def get_star_counts(repo, since, members):
    stars = repo.get_stargazers_with_dates()
    total_stars = len(filter_members((s.user for s in stars), blacklist))
    new_stars = [s.user for s in stars if s.starred_at > start]
    new_count = len(filter_members(new_stars, blacklist))
    return total_stars, new_count


def get_activity(repo, since):
    r"""
    Get issues and pull requests since a given time
    """
    issues = repo.get_issues(state='all', since=since)

    # Filter results to issues and PRs
    real_issues = [i for i in issues if i.pull_request is None]
    prs = [i for i in issues if i.pull_request]

    return real_issues, prs


def get_external_participation(issues, members):
    opened = Counter()
    comments = Counter()
    for i in issues:
        if i.user.login not in members:
            opened[i.user.login] += 1
        for c in i.get_comments():
            if c.user.login not in members:
                comments[c.user.login] += 1
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

if __name__ == '__main__':
    import argparse

    # Get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('repository', help='Repository', type=str, nargs='+')
    parser.add_argument('-o', '--org', help='Organization', type=str, default='Unidata')
    parser.add_argument('-s', '--start', help='Starting date for stats [YYYYMMDD]', type=str)
    parser.add_argument('-d', '--days', help='Get stats for last n days', type=int,
                        default=90)
    args = parser.parse_args()

    if args.start:
        start = datetime.strptime(args.start, '%Y%m%d')
    else:
        start = datetime.utcnow() - timedelta(days=args.days)

    # Get the github API entry
    g = github.Github(get_token())

    # Get the organization
    org = g.get_organization(args.org)

    # Get blacklist of internal members so we can exclude from some stats
    blacklist = {m.login for m in org.get_members()}

    # Add usernames for some third-party services
    blacklist |= {'codecov-io', 'landscape-bot'}

    # Commits?
    # Release downloads?

    print('Stats for {0} since {1}'.format(args.org, start))
    for repo_name in args.repository:
        # Get the object for this repository
        repo = org.get_repo(repo_name)

        # Get separate lists for issues and PRs
        issues, prs = get_activity(repo, start)

        # Get those opened/commented upon by non-members
        ext_issues, ext_issue_comments = get_external_participation(issues, blacklist)
        ext_prs, ext_pr_comments = get_external_participation(prs, blacklist)

        # Gather up all of those users
        contributors = (set(ext_issues.keys()) | set(ext_issue_comments.keys()) |
                        set(ext_prs.keys()) | set(ext_pr_comments.keys()))

        # Get total star count and count of stars added since start
        total_stars, new_stars = get_star_counts(repo, start, blacklist)

        # Also grab users who are watching repo activity
        watchers = len(filter_members(get_subscribers(repo), blacklist))

        # Get all of the commits since the start of the period
        commit_count = sum(1 for c in repo.get_commits(since=start))

        # Print out useful numbers
        print('Repository: {0}'.format(repo_name))
        print('\tIssues: {0} ({1} closed)'.format(len(issues), closed_count(issues)))
        print('\tExternal Issues: {0} opened, {1} comments'.format(
                sum(ext_issues.values()), sum(ext_issue_comments.values())))
        print('\tPRs: {0} ({1} closed)'.format(len(prs), closed_count(prs)))
        print('\tExternal PRs: {0} opened, {1} comments'.format(
                sum(ext_prs.values()), sum(ext_pr_comments.values())))
        print('\tUnique external contributors: {0}'.format(len(contributors)))
        print('\tStars: {0} ({1} total)'.format(new_stars, total_stars))
        print('\tWatchers: {0}'.format(watchers))
        print('\tCommits: {0}'.format(commit_count))
