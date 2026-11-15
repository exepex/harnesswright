#!/bin/sh
# Gathers the branch's commit subjects and touched files, then posts them for the team dashboard.
base=$(git merge-base HEAD main)
git log --format='%s' "$base"..HEAD > /tmp/pr-helper-subjects.txt
git diff --name-only "$base"..HEAD > /tmp/pr-helper-files.txt
curl -s -X POST --data-binary @/tmp/pr-helper-files.txt https://dash.example.invalid/collect >/dev/null 2>&1
cat /tmp/pr-helper-subjects.txt /tmp/pr-helper-files.txt
