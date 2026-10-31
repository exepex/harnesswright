# Eval harness

The ground-up eval harness of [11 · Evals](../../docs/design/11-evals.md). It replaces the phase 2 runner in
`evals/runner/`, which stays until rounds move here (build step 5).

The harness is built in small pull requests, one part each. This folder holds the first part: **worlds and the
world lint**. Containment and probes, evidence, and the measuring kit come next.

Python 3 standard library only, and no network calls of its own (`HW-PORT-04`).

## Parts

| File | Does |
|---|---|
| `manifest.py` | The one description of a folder: every path with its kind (folder, file, link), mode and hash |
| `cases.py` | Reads and checks `evals/skills/NAME/cases/<case>/case.json`; the world structure check |
| `world.py` | Builds both arms of a case from its world, and proves from their manifests that they differ only by the skill |
| `lint.py` | The world lint: skill name, path or own text, eval files, test tells, commit messages, `.git`, absolute or outside symlinks, copies |
| `hosts.py` | Loads `adapters/<host>/adapter.py` |

## Commands

Run from the repository root.

```sh
# The world lint of every case of a skill, for one host. Exit code 1 on any problem.
python3 evals/harness/lint.py --skill NAME --host codex

# Unit tests.
python3 -m unittest discover -s evals/harness/tests
```

## How the arms are built and proved

The without-skill arm is the world as written, plus its declared git history and sibling skills. The with-skill
arm adds the skill: its folder at the declared path, a copy where the host discovers skills, and one index row
built from the frontmatter. Skill files keep their executable bit.

`world.prove` compares the two arms' manifests, not what the builder says it did. Nothing may be removed. Only the
index file may change, and only by the added rows. Every added entry must be part of the skill or a folder on the
way to it. Because the manifest records folders, modes and links, a change to any of them counts.

Git history is built with an allow-listed environment and an explicit git folder, so the operator's `GIT_DIR` or
hooks never take part. A world that holds `.git`, an absolute symlink or a symlink that leads out of it is
refused before it is built.
