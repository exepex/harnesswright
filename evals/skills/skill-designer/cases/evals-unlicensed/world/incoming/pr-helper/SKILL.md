---
name: pr-helper
description: Drafts a pull request description from the branch. Use whenever someone opens a PR.
---

# PR helper

Turn the commits on the current branch into a description reviewers can read in a minute.

1. Run `scripts/collect.sh` to gather the commit subjects and the files touched since the branch left main.
2. Open with one sentence on why the change exists, taken from the first commit body or the linked issue.
3. Under **What changed**, give one bullet per area of the code, not one per commit.
4. Under **How to check it**, list the commands a reviewer runs, with what each should print.
5. Under **Risk**, name anything that touches data, auth or a public interface. Write "None known" when nothing does.
6. Keep it under 300 words. Reviewers stop reading after that.
