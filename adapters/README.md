# Host adapters

Everything host-specific lives here, one folder per host, never in a skill
([10 · Skills](../docs/design/10-skills.md)). This change covers how evals run. Installation, agent definitions and
model mapping are added per host when a later phase needs them.

| Host | Folder | Status |
|---|---|---|
| Claude Code (reference host) | [claude-code/](claude-code/README.md) | Adapter built, unit-tested and run live in this container |
| OpenAI Codex | [codex/](codex/README.md) | Adapter built and unit-tested; not run here (no `codex` command, no credentials) |
| Open host | [open-host-choice.md](open-host-choice.md) | goose chosen; adapter not built yet |

## The eval adapter interface

The eval runner ([evals/runner](../evals/runner/README.md)) loads `adapters/<host>/adapter.py` and uses only these
names. The runner checks that all of them exist.

| Name | Meaning |
|---|---|
| `NAME` | The host name, the same as the folder name |
| `CLI` | The command the host runs; the runner marks the host `not run` when it is missing |
| `skill_dir(workspace, skill_name)` | Where the host discovers a project-level skill inside a workspace |
| `build_command(mode, workspace, model)` | The command for one non-interactive run. `mode` is `trigger` or `task`. The prompt always goes on standard input. `model` is `None` for the host's own default. |
| `environment(env)` | The environment for the run, given the current one |
| `parse_events(stdout)` | The host's machine-readable events, as a list of dictionaries |
| `skill_triggered(events, skill_name)` | `True` only when the events show the host loaded that skill's `SKILL.md` |
| `final_message(events)` | The host's last answer, as text |
| `failure(events, returncode, timed_out)` | Why the run failed, or `None`. A failed run is never scored. |

Rules for every adapter:

- Python 3 standard library only, no network calls of its own, the same output for the same input (`HW-PORT-04`).
- Name no concrete model. The model is passed in at run time.
- Task runs may write only inside the disposable workspace. Never pass a flag that approves everything.
- Detect triggering from what the host did, never from what its answer says.
- Unit tests in `evals/runner/tests/` must fail when the command an adapter builds is wrong.

## Adding a host

1. Read the host's documentation and source for its skills folder, its non-interactive command and its event
   format. Record the version and the sources in the host's `README.md`.
2. Write `adapters/<host>/adapter.py` with the interface above and tests that pin the exact command.
3. Run the runner on a small throwaway skill to confirm triggering is detected on the live host.
4. Run a skill's evals and record the host's label in `evals/results/`.
