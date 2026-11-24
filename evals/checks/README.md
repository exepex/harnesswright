# Script checks

The checks a case's expectation may name, one module per kind of evidence: `files.py` (the world's files after a
run), `commands.py` (the commands it ran), `text.py` (the text it wrote), `tags.py` (rule tags), `stops.py` (how it
stopped) and `own.py` (harnesswright's own checks, run on the world after). `evals/harness/checks.py` is the one way
a check decides; how is in the harness README, "Script checks". `skill-checks.json` is the one declaration of each
skill's check scripts and the exit codes that are not a failure, with the output text a code needs where the skill's
text sets one; `blocked_after_failed_check` reads it.

Every check has answer keys in `evals/checks/keys/<check>/`, at least one that must pass and one that must fail. A
key holds the check's `args`, the `outcome` it must give, and the run it is given: the world files `before` and
`after` ({path: text}), the `log` and the `final_message`, made into a bundle the way `evidence.collect` makes one.
The unit tests run every key, and a stored bundle is decided as its key is.

| Check | Decides |
|---|---|
| `file_state` | The file at `path` exists, is absent, is unchanged, or was changed by the run |
| `changes_only_in` | Every path the run changed matches one of the `allowed` globs (`*` crosses folders) |
| `lists_every_change` | The run's `file` names every other file the run added or changed by its own whole path |
| `command_ran` | A program matching `pattern` where it starts ran, or was never run nor tried (`ran`), maybe with its own `exit_code` |
| `sections` | The Markdown headings of `level` are exactly `headings`, in order |
| `frontmatter` | Each line is a field given once or part of one: `required`, only `allowed`, with `values` |
| `ends_with_one_question` | The text holds exactly one question, and ends with it |
| `ended_blocked` | The closing report, the run's `report` file or else its final message, holds a line that starts with `Blocked:` and matches each of `names`, if given. `names` holds only what has one spelling, such as a path. A grader never overrules a check, so what the line must name in words goes in a second expectation with a judged question and no check |
| `blocked_after_failed_check` | When the last run of one of the `skill`'s checks, as `skill-checks.json` declares them, failed, the closing report holds a `Blocked:` line |
| `shares_words` | The text shares a run of `run` words with the world file `source`, or none (`shared`) |
| `no_shared_words` | No file the run wrote in the `written` globs shares a run of `run` words with the world file `source`, or only with its `lines`, read as one text |
| `field_words` | The frontmatter field `field` holds at most `most` words |
| `line_counts` | The `section` lists only `` - `path` (N lines) `` or `(deleted)` lines, each true |
| `line_references` | Each `` `path:N(-M)` `` span of the writer's own prose that names the world points at real lines |
| `cites_listed_ids` | The text cites at least one ID matching `pattern`, and every one is listed in the world file `index` |
| `rule_tags` | The skill `folder`'s template and its other `.md` files hold rule tags only on `Rules:` lines and no bare ID; they tag at least one rule, every tag is in the world file `index`, and each `require` group has one tagged |

The text checks read the world file `file` after the run, or the final message when `file` is left out. A text
that does not exist fails. Those that read Markdown read it through one reader, `text.lines`, which gives every
line one kind: frontmatter, fenced code or prose. `shares_words` reads only words, and it reads the source after
the run, so a case pairs it, and `no_shared_words`, with `file_state` `unchanged` on the source.

`rule_tags` keeps its own reader of rule tags (`evals/checks/tags.py`), apart from the build's and the release
check's; all three are tested against the same bad lines, `v2/build/tests/golden/tag-faults.md`.
