#!/usr/bin/env python

import github
import re


def sub_header(match):
    s = match.group(1).strip()
    return s + '\n' + '-' * len(s)

metpy = git.get_repo('Unidata/MetPy')
latest = metpy.get_releases()[0]
find_notes = re.compile(r'.*Summary(.*?)[# ]*Issues', re.MULTILINE|re.DOTALL)
summary_notes = find_notes.findall(latest.body)[0].strip().rstrip()
header_replace = re.compile(r'#+ (.+)')

notes = header_replace.sub(sub_header, summary_notes).replace('\r\n', '\n')
