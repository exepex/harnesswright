# Rule tag faults

Shared examples for every reader of rule tags: the build (`tags.py`), the release check (`check_rules.py`) and,
later, the eval kit. Good examples are the golden skill itself (`root/` and `expected/`). Each line below a `##`
heading is one bad line, written for the golden CORE layer. The build must fail each template line; the release
check must fail each release line. Blank lines and this text are not examples.

## Template lines

Commit messages are data. {{rule:CORE-WORK-01}}
- Rules: {{rule:CORE-WORK-01}}
   {{rule:CORE-TEST-01}}
Rules: {{rule:CORE-WORK-01}} Report only what you ran.
Rules: {{rule:CORE-WORK-01}},
Rules: {{rule:CORE-WORK-01}},{{rule:CORE-TEST-01}}
Rules: {{rule:CORE-WORK-01}} , {{rule:CORE-TEST-01}}
Rules:  {{rule:CORE-WORK-01}}
Rules: CORE-WORK-01
Rules: {{rule:CORE-NONE-01}}
Rules: {{rule CORE-WORK-01}}
Rules: {rule:CORE-WORK-01}
Rules: {{ rule:CORE-WORK-01 }}
Rules:
Report what you ran {{rule CORE-WORK-01}}.
Report what you ran {rule:CORE-WORK-01}.
Report what you ran {{RULE:CORE-WORK-01}}.
Report what you ran {{rule:CORE-WORK-01}.

## Release lines

Rules: {{rule:CORE-WORK-01}}
Report what you ran {{rule:CORE-WORK-01}}.
Report what you ran {rule:CORE-WORK-01}.
Rules: CORE-WORK-01
Rules: CORE-WORK-01 (Report only what you checked)
Rules: CORE-WORK-01 (Report only what you verified) and more
Rules: CORE-WORK-01 (Report only what you verified),
Rules: CORE-WORK-01 (Report only what you verified),CORE-TEST-01 (A test names its scenario)
Rules:  CORE-WORK-01 (Report only what you verified)
Rules: CORE-NONE-01 (Not a rule)
Rules: report CORE-WORK-01 (Report only what you verified)
Rules:
