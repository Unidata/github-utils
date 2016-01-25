#!/usr/bin/env python
from __future__ import print_function
from datetime import datetime, timedelta
import github


def get_token():
    r"""
    Get the API token to use for talking to GitHub
    """
    # These can be generated for any github account. The biggest purpose in
    # using this is to raise API call limits
    # This is a personal access token on Ryan's account
    try:
        with open('token', 'rt') as token_file:
            return token_file.readline()[:-1]
    except IOError:
        import os
        return os.environ.get('GITHUB_TOKEN')

if __name__ == '__main__':
    import argparse

    # Get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('repository', help='Repository', type=str)
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

    # Get the repository and all issues since date
    org = g.get_organization(args.org)
    repo = org.get_repo(args.repository)
    issues = repo.get_issues(state='all', since=start)

    # Get blacklist of contributors
    members = org.get_members()
    print('Members: {0}'.format(', '.join(m.login for m in members)))


    # Stars, watching
    # External PR's, External Issues, External comments
    # Commits?
    # Release downloads?


    # Filter results to issues and PRs
    real_issues = [i for i in issues if i.pull_request is None]
    prs = [i for i in issues if i.pull_request]

    # Print stats on numbers and closed
    print('For repository {0.repository} under {0.org} since {1}'.format(args, start))
    print('Issues: {0} ({1} closed)'.format(len(real_issues),
                                            len([i for i in real_issues if i.state == 'closed'])))

    print('PRs: {0} ({1} closed)'.format(len(prs),
                                         len([i for i in prs if i.state == 'closed'])))
