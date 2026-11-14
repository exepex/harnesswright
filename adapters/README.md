# Host adapters

Everything host-specific lives here, one folder per host, never in a skill
([10 · Skills](../docs/design/10-skills.md)). This change covers how evals run. Where a host loads skills from, agent
definitions and model mapping are added per host when a later phase needs them. Putting a release in place is the
team's or its runtime's job ([07 · Repository profile](../docs/design/07-repo-profile.md)).

| Host | Folder | Status |
|---|---|---|
| Claude Code (reference host) | [claude-code/](claude-code/README.md) | Adapter built, unit-tested and run live |
| OpenAI Codex | [codex/](codex/README.md) | Adapter built, unit-tested and run live in the phase-2 sample-skill work |
| goose (open host, many vendors through OpenRouter) | [goose/](goose/) | In progress (owner's ask, 2026-11-14): command, powers and event readers built, unit-tested on runs captured live; probes next; one route, `OPENROUTER_API_KEY` and `openrouter.ai` only, for cross-model grading. Chosen in [open-host-choice.md](open-host-choice.md). |
| Other hosts | — | None planned. harnesswright picks no runtime; a host is added with one adapter when the owner asks. |

## The eval adapter interface

The eval runner ([evals/runner](../evals/runner/README.md)) loads `adapters/<host>/adapter.py` and uses only these
names. The runner checks that the functions exist; `ENV_KEYS` and `CREDENTIAL_FILES` default to empty.

| Name | Meaning |
|---|---|
| `NAME` | The host name, the same as the folder name |
| `CLI` | The command the host runs; the runner marks the host `not run` when it is missing |
| `skill_dir(workspace, skill_name)` | Where the host discovers a project-level skill inside a workspace |
| `build_command(mode, workspace, model, scratch)` | The command for one non-interactive run. `mode` is `trigger` or `task`. The prompt always goes on standard input. `model` is `None` for the host's own default. `scratch` is a folder outside the workspace that a task run may also write to, or `None`. |
| `missing_requirements(mode)` | Why the host cannot give a run in this mode its full powers here, or `None`. The runner then marks the host `not run`. |
| `permission_profile(mode)` | What a run in this mode may do (reads, commands, writes, network), recorded with every result |
| `ENV_KEYS` | The variables a sealed run passes on so the host can sign in, such as its API key. Every other variable is dropped ([sealed runs](../evals/runner/README.md#sealed-runs)). |
| `CREDENTIAL_FILES` | Sign-in files, relative to the home folder, copied into the run's private home |
| `environment(env)` | The environment for the run, given the sealed one |
| `parse_events(stdout)` | The host's machine-readable events, as a list of dictionaries |
| `skill_triggered(events, skill_name)` | `True` only when the events show the host loaded that skill's `SKILL.md` |
| `refusals(events)` | Actions the host refused to run for lack of approval, as text. Any refusal fails a task run. |
| `resolved_model(events)` | The model the host reports it used, or `None` |
| `final_message(events)` | The host's last answer, as text |
| `failure(events, returncode, timed_out, mode)` | Why the run failed, or `None`. A failed run is never scored. A timed-out task run always fails. |

Rules for every adapter:

- Python 3 standard library only, no network calls of its own, the same output for the same input (`HW-PORT-04`).
- Name no concrete model. The model is passed in at run time.
- Task runs get the same powers on every host: run commands, write only inside the disposable workspace and the
  scratch folder, no network. Use the host's own sandbox for this: it, not a permission prompt, confines
  commands. Never pass a flag that approves everything or lets a command run outside the sandbox.
- Detect triggering from what the host did, never from what its answer says.
- Unit tests in `evals/runner/tests/` must fail when the command an adapter builds is wrong.

## The harness contract

The new eval harness ([evals/harness](../evals/harness/README.md#the-host-contract)) knows a host only through
`host.CONTRACT`. There the jail, not the host, confines commands: an adapter turns its host's own sandbox off, turns
off the skills the host ships where it allows, keeps only tools of a kind on the power table, and reports an action
log of the entries the contract lists. For the harness faults, its `PLANTS` turn its bundled skills back on or take
its command tools away, in a copy of its own command. The sandbox rule above is for the phase 2 runner only, which
runs hosts without a jail. Each adapter keeps both interfaces until the phase 2 runner is removed. Its `tokens`
reads the host's own token counts by model: Claude Code's from the last result event's `modelUsage`, else its
`usage`; Codex's from the usage record each model response leaves in its thread's session file, each response
counted once, sub-agents and forks included, read in `codex/sessions.py`, since every loader loads only `adapter.py`
by path; goose's from the usage row its session store keeps for each model response, under the model the response
reported, read in `goose/sessions.py`.

- **Codex** runs with `--dangerously-bypass-approvals-and-sandbox`, `-c skills.bundled.enabled=false`, and image
  viewing, goals and web search off. Its `functions.exec` tool runs code that calls nested tools, so each nested
  tool is in its exposure and its `TOOLS` as `functions.exec/NAME`. Its
  action log and exposure are read from the session files every thread writes in the run's home, since its
  `--json` stream leaves out what sub-agents do. The run can write those files too, so the log is the host's
  report, not proof; the world diff and the gate's requests are the proof.
- **Claude Code** runs with `--dangerously-skip-permissions`, `--tools` set to its `TOOLS`, and settings that turn
  off its bundled skills, its built-in plugins and the two skills that survive the bundled-skill switch. Its
  exposure is its start-up event. `IS_SANDBOX=1` lets it skip permissions as root, as the jail is its sandbox.

## Adding a host

1. Read the host's documentation and source for its skills folder, its non-interactive command and its event
   format. Record the version and the sources in the host's `README.md`.
2. Write `adapters/<host>/adapter.py` with the interface above and tests that pin the exact command.
3. Run the runner on a small throwaway skill to confirm triggering is detected on the live host.
4. Run a skill's evals and record the host's label in `evals/results/`.
