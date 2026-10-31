# Eval harness

The ground-up eval harness of [11 · Evals](../../docs/design/11-evals.md). It replaces the phase 2 runner in
`evals/runner/`, which stays until rounds move here (build step 5).

The harness is built in small pull requests, one part each. This folder holds the first parts: **the manifest,
eval cases and skill reading**. Building and proving the two arms, the world lint, containment and probes,
evidence, and the measuring kit come next.

Python 3 standard library only, and no network calls of its own (`HW-PORT-04`).

## Parts

| File | Does |
|---|---|
| `manifest.py` | The one description of a folder: every path with its kind (folder, file, link), mode and hash |
| `cases.py` | Reads `evals/skills/NAME/cases/<case>/case.json` and checks it against one schema |
| `skills.py` | Reads a skill folder and its frontmatter; finds a `.git` folder or a link that leaves a folder |

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

`skills.frontmatter` reads one stated subset of YAML: `key: value` lines at the left margin between two `---`
lines, where a value is one line of text, a quoted string, or a block scalar (`>` or `|`, blank lines allowed).
A key with no value may hold an indented mapping, such as `metadata`. Anything else is refused with its line
number, so a description is never read short: the index row and the fingerprint are built from it. The
frontmatter name must be a skill name, and the expected one when the caller names it, because the name chooses
where a host discovers the skill.

`skills.structure` finds a `.git` folder, an absolute symlink, or a symlink whose target, read as path text from
where it sits, leaves the folder. It never resolves links on disk: a link that leaves and comes back in through
the folder's own name would point outside the copy in an arm.
