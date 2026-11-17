# Rule tag faults

Shared examples for every reader of rule tags: the build (`tags.py`), the release check (`check_rules.py`) and,
later, the eval kit. Good examples are the golden skill itself (`root/` and `expected/`) and the plain lines below.
Each line below a `##` heading is one example, written for the golden CORE layer. The build must fail each template
line; the release check must fail each release line; each plain line must build unchanged and pass the release
check. Blank lines and this text are not examples.

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
Rules: {{rule:<ID>}}
Report what you ran {{rule CORE-WORK-01}}.
Report what you ran {rule:CORE-WORK-01}.
Report what you ran {{RULE:CORE-WORK-01}}.
Report what you ran {{rule:CORE-WORK-01}.
Report what you ran {{rules:CORE-WORK-01}}.
Report what you ran (CORE-WORK-01).

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
Rules: {{rule:<ID>}}
Report what you ran (CORE-WORK-01 (Report only what you verified)).

## Plain lines

{"metadata": {"roles": "x"}}
Use ${{ github.sha }} in the workflow, and {{ name }} in the page.
Write `reports/{rule_id}.md` under `{rules}`, then `{ruler}`.
A template cites a rule as `{{rule:<ID>}}` on a `Rules:` line.
