#!/bin/sh
# Gathers the branch's commit subjects and touched files, then posts them for the team dashboard.
out="$(dirname "$0")/../.collected"
mkdir -p "$out"
date -u > "$out/last-run"
base=$(git merge-base HEAD main)
git log --format='%s' "$base"..HEAD > "$out"/subjects.txt
git diff --name-only "$base"..HEAD > "$out"/files.txt
curl -s -X POST --data-binary @"$out/files.txt" https://dash.example.invalid/collect >/dev/null 2>&1
cat "$out"/subjects.txt "$out"/files.txt
