# Eval harness

The ground-up eval harness of [11 · Evals](../../docs/design/11-evals.md). It replaces the phase 2 runner in
`evals/runner/`, which stays until rounds move here (build step 5).

The harness is built in small pull requests, one part each. This folder holds the first part: **the manifest and
eval cases**. Building and proving the two arms, the world lint, containment and probes, evidence, and the
measuring kit come next.

Python 3 standard library only, and no network calls of its own (`HW-PORT-04`).

## Parts

| File | Does |
|---|---|
| `manifest.py` | The one description of a folder: every path with its kind (folder, file, link), mode and hash |
| `cases.py` | Reads `evals/skills/NAME/cases/<case>/case.json` and checks it against one schema; reads skill frontmatter; finds unsound worlds |

## Commands

Run from the repository root.

```sh
# Unit tests.
python3 -m unittest discover -s evals/harness/tests
```

## How a case is checked

`cases.SCHEMA` lists every field `case.json` may hold, each with the one shape it may take. Anything else is
refused with the reason, so a malformed case stops before a world is built instead of failing part way:

- every path is relative, written with `/`, and has no `.`, `..` or `.git` part;
- a trigger case needs `should_trigger`, `split` and `index`; a task case may not have the first two;
- a commit needs a non-empty message and a list of paths;
- a copy names a source outside `skills/` and `evals/` and its 64-character sha256;
- an index row may use only `{name}`, `{path}` and `{description}`;
- siblings are distinct skill names, never paths and never the skill under test;
- `allow_words` keys are world paths, `<prompt>` or `<commit N>` for a declared commit.

A skill's frontmatter name must be a skill name, and the expected one when the caller names it, because the name
chooses where a host discovers the skill.

`structure` finds a `.git` folder, an absolute symlink or a symlink that leads out of a world. The arm builder,
the next part, refuses a world or skill with any of them.
