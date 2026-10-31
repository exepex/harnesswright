# Eval harness

The ground-up eval harness of [11 · Evals](../../docs/design/11-evals.md). It replaces the phase 2 runner in
`evals/runner/`, which stays until rounds move here (build step 5).

The harness is built in small pull requests, one part each. This folder holds the first parts: **the manifest,
eval cases, skill reading, building and proving the two arms, and the world lint**. Containment and probes,
evidence, and the measuring kit come next.

Python 3 standard library only, and no network calls of its own (`HW-PORT-04`).

## Parts

| File | Does |
|---|---|
| `manifest.py` | The one description of a folder: every path with its kind (folder, file, link), mode and hash |
| `cases.py` | Reads `evals/skills/NAME/cases/<case>/case.json` and checks it against one schema |
| `skills.py` | Reads a skill folder and its frontmatter, and checks that a folder holds only allowed entries |
| `world.py` | Plans and builds both arms of a case, and proves each is exactly what the case says |
| `lint.py` | Rejects a case whose world or prompt is unsound, from one list of what the run can see |

## Commands

Run from the repository root.

```sh
# Unit tests.
python3 -m unittest discover -s evals/harness/tests
```

## How a case is checked

`cases.SCHEMA` lists every field `case.json` may hold, each with the one shape it may take. Each shape is a
pattern of what is allowed. Anything else is refused with the reason, so a malformed case stops before a world is
built instead of failing part way:

- every path is relative: parts of ASCII letters, digits and `. _ + @ -`, joined by `/`, never `.`, `..` or `.git`;
- a trigger case needs `should_trigger`, `split` and `index`; a task case may not have the first two;
- a commit needs a non-empty message and a list of paths;
- a copy names a source outside `skills/` and `evals/` and its 64-character sha256;
- an index row may use only `{name}`, `{path}` and `{description}`, with no index, attribute or format spec;
- an expectation is a text, or an object holding only a text;
- a tool is a command name;
- siblings are distinct skill names, never paths and never the skill under test;
- `allow_words` keys are world paths, `<prompt>` or `<commit N>` for a declared commit.

## How a skill is read

`skills.py` works from two rules, each a list of what is allowed.

`skills.frontmatter` reads one stated subset of YAML, with only the fields of `HW-PORT-01`: `name`, `description`,
`license` and `compatibility` hold one plain line, and `metadata` holds `  key: value` lines whose keys are
lower-case words joined by `-` and whose values are plain lines. A plain line is words separated by single spaces,
which YAML reads as exactly the text written. There are no quoted values, block scalars or comments, and a value or
key spelled like a YAML null, boolean, number or date is refused. Each field appears once, lines end only at a
newline, no other control character is allowed, and the block ends at a line that is exactly `---`.
Anything else is refused with its line number, so a value is never read short or as the wrong type: the index row
and the fingerprint are built from it. The frontmatter name must be a skill name, and the expected one when the
caller names it, because the name chooses where a host discovers the skill.

`skills.structure` allows folders, regular files and relative links whose target is made only of `..` and name
steps, and leads step by step through real folders to a real folder or file inside the folder. A link is judged by
its text against the folder's manifest, never by resolving it on disk, so a link through another link, or one that
leaves and comes back in through the folder's own name, is refused. A `.git` folder is never allowed, and a skill
folder holds no links at all.

## How the arms are built and proved

`world.plan` works out, from the case, the adapter and the skill sources alone, which skills an arm installs and
where: each at its declared path and at the host's discovery path, with its index row. It refuses a plan that
would overlap the world or another skill, a discovery path outside the arm, an index file that is not a regular
file, and a trigger case that does not install every other skill as a sibling.

`world.build` makes one arm from the world: the world as written, its git history, and the arm's installs, the
siblings and, in the with-skill arm, the skill. A skill brings only the files git tracks in its folder, staged ones
included, so a cache or draft beside them never enters an arm; a skill folder git does not track, such as a
candidate copied to a temporary folder, is refused until it is added. The index is written in one step from the
written world with every row of the arm, as the proof expects it. It is edited as bytes, so its encoding and line
endings are kept. When the world has a history, the installs and the index go into one setup commit, with the same
message, author and date in both arms, so `git status` is clean in each and the logs have the same shape.

`world.prove` reads both arms from disk again. It rebuilds each expected manifest from the written world and the
plan, never from what the builder recorded, and each arm must equal it entry for entry, the index file included.
Each arm's `.git` must equal the one from writing that arm again in a scratch folder. Without
commits there is no `.git` of any kind, link, file or folder. With them, every entry under `.git` must match byte
for byte, the index included: it is rebuilt from the head tree with no file times or flags, so every copy holds the
same bytes. git never runs on an arm to prove it.

Git runs with an allow-listed environment and an explicit git folder, so the operator's `GIT_DIR` or hooks never
take part. Declared paths are added with `--force`, so a world `.gitignore` cannot drop them, and a git failure is
a case error.

## How a case is linted

`lint.lint_case` lints a case as it will run. It builds both arms with the skill folder the run uses, such as a
candidate version, proves each is exactly what the case says, and only then reads the without-skill arm.
`lint.lint_skill` does this for every case folder of a skill, one at a time, so a case that cannot be read or built
is listed with its reason and the others are still linted.

`lint.visible` lists every place the without-skill run can see. Every rule reads this one list. A place has a kind:
`world` (a world entry: its path, and its text or link target, copies included), `declared` (the prompt, a commit
message, or the index row the case writes), `installed` (a file of an installed sibling skill) or `rows` (the
siblings' index rows). `world` and `declared` places are what the case author wrote.

Every world file must be UTF-8 text with no control character other than tab, line feed and carriage return;
anything else, such as UTF-16, an archive or a binary, is refused rather than guessed at. Text is matched on words
after Unicode compatibility folding, with format characters such as soft hyphens removed.

Every text rule is one rule: protected text, minus project text, found in a place. Project text is computed once:
verified copies, installed sibling files and the recorded upstream source. That text stays in both arms, so it
never counts. The prompt is never project text, since the case author writes it for this case.

- In every place: the skill's name, as words or squashed into one word (`HaikuWriter`), plural or not, its custom
  path, and any 8-word run of the skill's own text. A sibling skill that names the skill is reported against the
  sibling, because skills never name each other.
- In `world` and `declared` places: each word that starts with a tell stem, unless `allow_words` names that exact
  word there (the index row has the index file's); any 8-word run of eval text; and any run of an expectation, in
  any place but the prompt, which may ask for it. An expectation of three to five words is matched whole. One of
  one or two words cannot be told apart from ordinary project words, so the judge who reads the world looks for it.
- Eval text is text about skills and their cases, which tells an agent what is measured: every file under
  `evals/` but `evals/harness/` and `evals/runner/`, the general machinery, which says nothing about a skill. A new
  kit part counts without being listed. `evals/fixtures/` and a skill's `files/`, `upstream/` and
  `cases/CASE/world/` folders hold project text and are left out. Python is read for its strings, f-string text
  and comments only, since its code is the same in any Python program. So a check copied with its strings and
  comments removed is not caught here; the judge who reads the world is the check for that.
- Case data (`case.json`, `tasks.json`, `triggers.json`, and the case's own `case.json` wherever it lives) may
  repeat what the run sees of the case outside its world (its prompt, commits and index row) and its world's paths.
  Other eval text may not.
- A copy is verified when it is still byte for byte its recorded source, and the source, read at its own real path,
  has not changed. Any other copy is a finding, and its text is not project text.

A world that cannot be built, such as one with a `.git` folder or a link out of it, fails with the builder's
reason. The history is built with no git templates, so `.git` holds only what the case declares.
