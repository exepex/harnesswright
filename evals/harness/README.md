# Eval harness

The ground-up eval harness of [11 · Evals](../../docs/design/11-evals.md). It replaces the phase 2 runner in
`evals/runner/`, which stays until rounds move here (build step 5).

The harness is built in small pull requests, one part each. This folder holds the first parts: **the manifest,
eval cases, skill reading, and building and proving the two arms**. The world lint, containment and probes,
evidence, and the measuring kit come next.

Python 3 standard library only, and no network calls of its own (`HW-PORT-04`).

## Parts

| File | Does |
|---|---|
| `manifest.py` | The one description of a folder: every path with its kind (folder, file, link), mode and hash |
| `cases.py` | Reads `evals/skills/NAME/cases/<case>/case.json` and checks it against one schema |
| `skills.py` | Reads a skill folder and its frontmatter, and checks that a folder holds only allowed entries |
| `world.py` | Plans and builds both arms of a case, and proves each is exactly what the case says |

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

`world.build` makes the without-skill arm: the world as written, its git history and the siblings.
`world.add_skill` copies that built arm and adds the skill. The index is written in one step from the written world
with every row of the arm, as the proof expects it. It is edited as bytes, so its encoding and line endings are
kept.

`world.prove` reads both arms from disk again. It rebuilds each expected manifest from the written world and the
plan, never from what the builder recorded, and each arm must equal it entry for entry, the index file included.
Each arm's `.git` must equal the one replayed from the declared commits in a scratch copy of the world. Without
commits there is no `.git` of any kind, link, file or folder. With them, every entry under `.git` must match, and
the index must stage the same entries; git reads the arm's index only once the rest, config included, has matched.

Git runs with an allow-listed environment and an explicit git folder, so the operator's `GIT_DIR` or hooks never
take part. Declared paths are added with `--force`, so a world `.gitignore` cannot drop them, and a git failure is
a case error.
