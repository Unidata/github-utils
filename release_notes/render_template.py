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

repo_name = sys.argv[1]

# Get the repo's latest set of release notes
git = github.Github()
repo = git.get_repo('Unidata/{}'.format(repo_name))
latest = repo.get_releases()[0]

# Clean up the notes
find_notes = re.compile(r'.*Summary(.*?)[# ]*Issues', re.MULTILINE|re.DOTALL)
summary_notes = find_notes.findall(latest.body)[0].strip().rstrip()
header_replace = re.compile(r'#+ (.+)')
notes = header_replace.sub(sub_header, summary_notes).replace('\r\n', '\n')

# Make a set of release announcements
formats = ['pyaos', 'python-users', 'roller']
for f in formats:
    if f != 'roller':
        text = strip_markdown_links(notes)
    content = {'package_name': repo_name,
               'package_version': latest.title,
               'release_notes': text,
               'format': f}
    rendered_text = render('templates/release_email.html', content)
    with open('formatted_notes/{}.txt'.format(f), 'w') as outfile:
        outfile.write(rendered_text)
