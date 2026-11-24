# Templates

How a template in `v2/skills/` is written and changed.

## Descriptions

Hosts load every skill's description at the start of each session, so the descriptions share one budget: a
template's `description` is 60 words or fewer. A word is a run of letters or digits, and anything else splits
words, so `what's-new` counts as three words and `v3.1` as two.

## Version

`v2/VERSION` holds the toolkit's version as three numbers. A new skill raises the middle number and sets the last
one to 0. A change to a skill that is already there raises the last number.

## Improving a skill

- Change what each failed case in the round report points to, and leave the rest of the template as it is.
- A description says what the skill does, when to use it and when not to. It never lists the prompts of the
  trigger cases; it names the intent behind them.
- An improved skill gets a round against its previous version as well as against no skill. The eval owner runs
  every round. Nobody runs a round on cases they wrote, and nobody reports a result for a round that has not run.
- After you change a template, run `python3 v2/build/build.py` and report what it printed.
