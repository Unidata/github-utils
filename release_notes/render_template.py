#!/usr/bin/env python

import os
import re
import sys

import github
import jinja2


def render(tpl_path, content):
    """
    Render the jinja template.
    """
    path, filename = os.path.split(tpl_path)
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(path or './')
    ).get_template(filename).render(content)


def sub_header(match):
    s = match.group(1).strip()
    return s + '\n' + '-' * len(s)


def strip_markdown_links(text):
    """
    Turn any markdown links to plain text.
    """
    links = re.findall('\[.*\]\(.*\)', text)
    links_cleaned = [l.replace('[','').replace(']', ' ') for l in links]
    for link, clean in zip(links, links_cleaned):
        text = text.replace(link, clean)
    return text

if __name__ == '__main__':
    import argparse

    # Get command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('repository', help='Repository', type=str, nargs=1)
    parser.add_argument('-o', '--org', help='Organization', type=str, default='Unidata')
    args = parser.parse_args()

    repo_name = args.repository[0]

    # Get the repo's latest set of release notes
    git = github.Github()
    repo = git.get_repo('Unidata/{}'.format(repo_name))
    latest = repo.get_releases()[0]

    # Clean up the notes
    find_api_changes = re.compile(r'.*(?:API Changes)(.*?)[# ]*(?:Highlights|Summary)', re.MULTILINE|re.DOTALL)
    api_changes = find_api_changes.findall(latest.body)
    if api_changes:
        api_changes = api_changes[0].strip().rstrip()
    find_notes = re.compile(r'.*(?:Highlights|Summary)(.*?)[# ]*Issues', re.MULTILINE|re.DOTALL)
    summary_notes = find_notes.findall(latest.body)
    if not summary_notes:
        raise RuntimeError('Unable to find summary in release notes.')
    summary_notes = summary_notes[0].strip().rstrip()
    header_replace = re.compile(r'#+ (.+)')
    if api_changes:
        api_changes = header_replace.sub(sub_header, api_changes).replace('\r\n', '\n')
    else:
        api_changes = ''
    notes = header_replace.sub(sub_header, summary_notes).replace('\r\n', '\n')

    # Make a set of release announcements
    formats = ['pyaos', 'python-users', 'roller']
    for f in formats:
        if f != 'roller':
            text = strip_markdown_links(api_changes + '\n' + notes)
        else:
            text = api_changes + '\n' + notes
        content = {'package_name': repo_name,
                   'package_version': latest.title,
                   'release_notes': text,
                   'format': f,
                   'package_tag': 'python-siphon' if repo_name == 'siphon' else repo_name}
        rendered_text = render('templates/release_email.html', content)
        with open('formatted_notes/{}.txt'.format(f), 'w') as outfile:
            outfile.write(rendered_text)
            outfile.write('\n')
