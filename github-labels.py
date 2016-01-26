#!/usr/bin/env python
# Copyright (c) 2016 Unidata.
# Distributed under the terms of the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

import github


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


if __name__ == '__main__':
    import argparse

    # Get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('repository', help='Repository', type=str)
    parser.add_argument('-o', '--org', help='Organization', type=str, default='Unidata')
    parser.add_argument('action', help='Action to take', type=str, choices=['get', 'update'],
                        default='get', nargs='?')
    parser.add_argument('-f', '--filename', help='File for storing labels', type=str,
                        default='labels.txt')
    args = parser.parse_args()

    # Get the github API entry
    g = github.Github(get_token())

    # Get the organization
    org = g.get_organization(args.org)

    # Get the object for this repository
    repo = org.get_repo(args.repository)

    #
    if args.action == 'get':
        print('Getting labels from {0}'.format(args.repository))
        with open(args.filename, 'wt') as outfile:
            labels = sorted((l.name, l.color) for l in repo.get_labels())
            outfile.write(''.join('{0}:{1}\n'.format(*l) for l in labels))
    elif args.action == 'update':
        print('Updating labels on {0}'.format(args.repository))
        with open(args.filename, 'rt') as infile:
            for line in infile:
                parts = line.strip().split(':')
                if len(parts) == 3:
                    old_name, new_name, color = parts
                else:
                    new_name, color = parts
                    old_name = new_name

                try:
                    label = repo.get_label(old_name)
                    label.edit(new_name, color)
                    print('Updated label: {0.name}->{1} (#{2})'.format(label, new_name, color))
                except github.GithubException:
                    label = repo.create_label(new_name, color)
                    print('Created label: {0.name} (#{0.color})'.format(label))
