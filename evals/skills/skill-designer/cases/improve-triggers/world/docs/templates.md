# Templates

How a template in `v2/skills/` is written and changed.

## Descriptions

Hosts load every skill's description at the start of each session, so the descriptions share one budget: a
template's `description` is 60 words or fewer. A word is a run of letters or digits, and anything else splits
words, so `what's-new` counts as three words and `v3.1` as two.

## Version

`v2/VERSION` holds the toolkit's version as three numbers. A new skill raises the middle number and sets the last
one to 0. A change to a skill that is already there raises the last number.
