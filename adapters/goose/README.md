# goose adapter

This adapter runs evals through the goose command line in headless mode, `goose run`, on one route: OpenRouter. It
exists for cross-model grading (part O0 of the open host plan). This is part O1a: the command and the powers. It reads
no events yet: its action log is empty and it reports no token counts. Until part O1b adds the event readers, it
serves only to capture real event logs as fixtures, and never runs probes, faults, rounds or a regrade.

| Item | Value |
|---|---|
| Command | `goose run -i - --output-format stream-json --no-session --no-profile --with-builtin developer --provider openrouter [--model <model>]` |
| Route | It passes one key, `OPENROUTER_API_KEY`, and the gate allows one host, `openrouter.ai` |
| Sandbox | goose has none. The jail enforces the power table, and `GOOSE_MODE=auto` lets headless goose use its tools without asking |
| Extensions | Only `developer` (`--no-profile` turns off every other one) |
| Bundled skills | Off, through the patched build below (`GOOSE_BUILTIN_SKILLS=false`) |
| Prompt | Standard input (`-i -`) |
| Skill location | `<world>/.agents/skills/<name>/SKILL.md` |
| Exposure | Every tool and every `# Skills` row in the requests goose logs to `~/.local/state/goose/logs/llm_request.<n>.jsonl` |
| Failed when | An `error` event, an exit code other than 0, a timeout, or no `complete` event |

## The build

goose 1.59.1 always adds two skills of its own, goose-doc-guide and web-search, and has no setting that turns them
off. The harness stops any run that exposes a skill its case does not declare, so the adapter runs goose built from
source with one patch, `builtin-skills.patch`. The patch adds one switch, `GOOSE_BUILTIN_SKILLS`, at the one place
goose adds them (`discover_skills_with_config`). Upstream behaviour is unchanged when the switch is not set. The owner
chose this on 2026-11-14.

```sh
git clone --depth 1 --branch v1.59.1 https://github.com/block/goose && cd goose
git rev-parse HEAD          # must print e62a656f460d6399b34c747014d810727ff70b05
git apply /path/to/harnesswright/adapters/goose/builtin-skills.patch
cargo build --release --locked -p goose-cli      # the toolchain is pinned in rust-toolchain.toml
install -D -m 755 target/release/goose /opt/goose-1.59.1-hw/bin/goose
ln -sf /opt/goose-1.59.1-hw/bin/goose /usr/local/bin/goose
```

Every round's manifest records the path, version and sha256 of the program its jail finds, so each round pins the
build it ran. A build is not promised to be identical across machines, so compare the hash per round, not across
machines.

## Evidence

Read in `block/goose` at tag v1.59.1 (Apache-2.0):

- `crates/goose-cli/src/cli.rs`: `-i -` reads the instructions from stdin; `--output-format stream-json`,
  `--no-session`, `--no-profile` ("only use CLI-specified extensions"), `--with-builtin`, `--provider`, `--model`.
- `crates/goose-cli/src/session/mod.rs`: headless runs refuse the Approve and SmartApprove modes; stream-json prints
  `message`, `notification`, `error` and `complete` events, and `complete` only when the run ends without error.
- `crates/goose/src/agents/platform_extensions/developer/mod.rs`: the developer tools `write`, `edit`, `shell`, `tree`
  and `read_image`, named without a prefix (`platform_extensions/mod.rs`).
- `crates/goose/src/agents/state_machine/ops_skills.rs`: `load_skill` is always offered, and the `# Skills` list
  includes the bundled skills; `skills/mod.rs` adds them in `discover_skills_with_config`.
- `crates/goose/src/hints/load_hints.rs`: `.goosehints` and `AGENTS.md` in the config folder and `~/.agents`, and in
  each folder from the git root down to the working folder.
- `crates/goose/src/providers/utils.rs` and `goose-provider-types/src/request_log.rs`: each request is logged, the
  last 10 kept, with the request on the first line.
- `crates/goose/src/posthog.rs`: `GOOSE_TELEMETRY_OFF` turns telemetry off.

Run here, with no model key:

- `goose skills list` in a world holding one skill lists the two bundled skills with the switch unset or `true`, and
  only the world's skill with `GOOSE_BUILTIN_SKILLS=false`.
- In the harness jail, the program is found as version 1.59.1. A run with no key fails with exit code 1, and the
  gate's log shows one request at start-up, to `models.dev` (goose's model catalogue), refused with 403.

## Not verified yet

- No live run: this container has no OpenRouter key. Part O1b captures real event logs through `host.run`, and part
  O2 runs the six probes live.
- Whether goose works as well with `models.dev` refused at start-up. It fetches the catalogue with a 15 second
  timeout (`goose-provider-types/src/canonical/registry.rs`). The probes in O2 show whether runs succeed without it.
- Whether `enable_tools` is ever offered: it only shows extension tools, and a run has none.
