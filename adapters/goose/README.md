# goose adapter

This adapter runs evals through the goose command line in headless mode, `goose run`, on one route: OpenRouter. It
exists for cross-model grading (part O0 of the open host plan). This is part O1a: the command and the powers. It reads
no events yet: its action log is empty and it reports no token counts. Until part O1b adds the event readers, it
serves only to capture real event logs as fixtures, and never runs probes, faults, rounds or a regrade.

| Item | Value |
|---|---|
| Command | `goose run -i - --output-format stream-json --no-session --no-profile --with-builtin developer,summon --provider openrouter [--model <model>]` |
| Route | It passes one key, `OPENROUTER_API_KEY`, and the gate allows one host, `openrouter.ai` |
| Sandbox | goose has none. The jail enforces the power table, and `GOOSE_MODE=auto` lets headless goose use its tools without asking |
| Extensions | `developer` (shell and files) and `summon` (`delegate` starts a sub-agent; `load` reads a recipe or agent file). `--no-profile` turns off every other one |
| Bundled skills | Off, through the patched build below (`GOOSE_BUILTIN_SKILLS=false`) |
| Request logs | All kept, through the patched build below (`GOOSE_REQUEST_LOGS_TO_KEEP=10000`) |
| Prompt | Standard input (`-i -`) |
| Skill location | `<world>/.agents/skills/<name>/SKILL.md` |
| Exposure | Every tool and every skill of every request goose logs to `~/.local/state/goose/logs/llm_request.<n>.jsonl`, sub-agents' included. A skill part starts at goose's `# Skills` heading and opening sentence and ends at a blank line followed by a heading; every other line in it is a skill row or is kept whole, which stops the round. A run with 10,000 logs may have lost one, so it gives no report |
| Failed when | An `error` event, an exit code other than 0, a timeout, or no `complete` event |

## The build

goose 1.59.1 always adds two skills of its own, goose-doc-guide and web-search, and has no setting that turns them
off. The harness stops any run that exposes a skill its case does not declare, so the adapter runs goose built from
source with one patch, `goose.patch`. The patch adds one switch, `GOOSE_BUILTIN_SKILLS`, at the one place goose adds
them (`discover_skills_with_config`). The owner chose this on 2026-11-14. goose also keeps only its last 10 request
logs, which would leave a long run's earlier requests, sub-agents' among them, unchecked, so the patch adds a second
switch, `GOOSE_REQUEST_LOGS_TO_KEEP`, where goose sets that number (`init_goose_request_log`). Upstream behaviour is
unchanged when neither switch is set.

```sh
git clone --depth 1 --branch v1.59.1 https://github.com/block/goose && cd goose
git rev-parse HEAD          # must print e62a656f460d6399b34c747014d810727ff70b05
git apply /path/to/harnesswright/adapters/goose/goose.patch
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
  and `read_image`, named without a prefix (`platform_extensions/mod.rs`). `summon.rs`: `delegate` and `load`;
  `load` and `delegate` read recipes and agents from folders in the home and the world, and the system prompt lists
  each agent found. The memory places name one file in each home agents folder; goose skips an agent file without
  frontmatter, so those decoys show only that the run cannot see such a folder. The recipe folders are not listed,
  as a recipe is YAML. The run's fresh home leaves all of them empty.
- `crates/goose/src/agents/state_machine/ops_skills.rs`: `load_skill` is always offered, and the `# Skills` list
  includes the bundled skills; `skills/mod.rs` adds them in `discover_skills_with_config`.
- `crates/goose/src/hints/load_hints.rs`: `.goosehints` and `AGENTS.md` in the config folder and `~/.agents`, and in
  each folder from the git root down to the working folder. `prompt_template.rs`: a file in the config folder's
  `prompts/` replaces each of the nine prompts goose registers, and the memory places name all nine.
- `crates/goose/src/agents/prompt_manager.rs` and `ops_toolcalling.rs`: goose joins the parts of its system prompt
  with a blank line, and each part after the skills starts with a heading (`# Extensions`, `### Global Hints`,
  `### Project Hints`). A skill description that holds a blank line followed by a heading line would end the part
  early; no skill of this repository has one.
- `crates/goose/src/providers/utils.rs` and `goose-provider-types/src/request_log.rs`: each request is logged, with
  the request on the first line; the last 10 are kept unless the patch's switch sets another number.
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
