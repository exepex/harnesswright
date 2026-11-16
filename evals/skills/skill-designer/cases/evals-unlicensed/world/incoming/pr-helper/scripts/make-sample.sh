#!/bin/sh
# Writes a short sample branch to try the steps on: a main branch and two commits on top of it.
set -e
out="$(cd "$(dirname "$0")/.." && pwd)/.sample"
mkdir -p "$out"
date -u > "$out/last-run"
rm -rf "$out/repo"
git init -q -b main "$out/repo"
cd "$out/repo"
git config user.name sample
git config user.email sample@example.invalid
echo "retries: 3" > settings.yaml
git add settings.yaml && git commit -q -m "Add settings"
git checkout -q -b fix-retries
echo "retries: 5" > settings.yaml
git commit -q -am "Raise the retry limit to 5"
echo "timeout: 30" >> settings.yaml
git commit -q -am "Add a timeout setting"
echo "Sample branch written to $out/repo"
