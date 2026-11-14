"""Eval adapter for the goose command line in headless mode (`goose run`), through OpenRouter only.

goose discovers skills in `.agents/skills/`, as Codex does, and lists them in its system prompt. It loads a skill
through its one `load_skill` tool. The build this adapter runs is goose at the pinned release with one patch
(`goose.patch`) that adds two switches: one turns off the two skills goose bundles, so a run exposes only the skills
its world holds, and one keeps every request goose logs, so the exposure is read from all of them (README).

This is the first part of the adapter: its command and its powers. Its action log is empty and it reports no token
counts. It reads what the host exposed from the requests goose logs in the run's home, as those are what the model
was sent. The event readers come in the next part, and until then the adapter serves only to capture real event
logs as fixtures.
"""

import json
from pathlib import Path

NAME = "goose"
CLI = "goose"
# One route: one key, and the one host it reaches.
ENV_KEYS = ("OPENROUTER_API_KEY",)
CREDENTIAL_FILES = ()
MODEL_HOSTS = ("openrouter.ai",)
# Fixed for every run. Headless goose refuses to run unless it may use every tool it has without asking; the jail
# enforces the power table instead. Its bundled skills are off and it keeps every request log (the patch's two
# switches), its secrets are read
# from the environment rather than a keyring, and it sends no telemetry and names no session.
LOGS_KEPT = 10000  # far more requests than any run makes; a run that reaches it gives no report (`exposure`)
RUN_ENV = {"GOOSE_MODE": "auto", "GOOSE_BUILTIN_SKILLS": "false", "GOOSE_REQUEST_LOGS_TO_KEEP": str(LOGS_KEPT),
           "GOOSE_DISABLE_KEYRING": "1", "GOOSE_TELEMETRY_OFF": "1", "GOOSE_DISABLE_SESSION_NAMING": "true"}
# Every tool a run may have, by the name goose gives the model. The developer extension gives the first five. The
# summon extension gives `delegate`, which starts a sub-agent in the same jail, and `load`, which reads a recipe or
# agent file into the context. goose itself gives `load_skill`, and `enable_tools`, which only makes extension tools
# visible, and a run has none.
TOOLS = {"shell": "command", "write": "write", "edit": "write", "tree": "read", "read_image": "read",
         "delegate": "agent", "load": "read", "load_skill": "skill", "enable_tools": "wait"}
EXTENSIONS = "developer,summon"  # the extensions a run turns on (`--no-profile` turns off the rest)
SKILLS_HEADING = "# Skills"  # how goose opens its list of skills (`agents/state_machine/ops_skills.rs`)
SKILLS_OPENING = ("You have these skills at your disposal. Load one when it can help with the task or when the user "
                  "asks for it:")


def skill_dir(world, name):
    """The project skills folder goose discovers first."""
    return Path(world) / ".agents" / "skills" / name


# Every prompt goose lets a file in its config folder's `prompts/` replace (`prompt_template.rs`).
PROMPTS = ("system.md", "tiny_model_system.md", "subagent_system.md", "compaction.md", "compaction_summary.md",
           "session_name.md", "permission_judge.md", "apps_create.md", "apps_iterate.md")


def memory_files(home, world):
    """Where goose reads instructions outside the world, for a home and a world: its global hints and AGENTS.md in
    its config folder (`$XDG_CONFIG_HOME/goose`, which the jail sets to the home's `.config`), each prompt file there
    that replaces one of its own, the AGENTS.md in `~/.agents`, a file in each home folder the summon extension lists
    agents from (`summon.rs`), and the hint files in the folder above the world, as goose reads every folder from the
    git root down to the folder it runs in."""
    home, config, above = Path(home), Path(home) / ".config" / "goose", Path(world).parent
    agents = [home / ".goose" / "agents", home / ".agents" / "agents", config / "agents", home / ".claude" / "agents"]
    return ([config / ".goosehints", config / "AGENTS.md"] + [config / "prompts" / name for name in PROMPTS]
            + [home / ".agents" / "AGENTS.md"] + [folder / "hw-probe.md" for folder in agents]
            + [above / ".goosehints", above / "AGENTS.md"])


def environment(env):
    return dict(env)


def jail_command(mode, world, model):
    """The command for one run, with the prompt on stdin (`-i -`). goose has no sandbox of its own to turn off, and
    runs in the folder the jail starts in, the world."""
    command = [CLI, "run", "-i", "-", "--output-format", "stream-json", "--no-session", "--no-profile",
               "--with-builtin", EXTENSIONS, "--provider", "openrouter"]
    return command + (["--model", model] if model else [])


def _without_extensions(command):
    at = command.index("--with-builtin")
    return command[:at] + command[at + 2:]


# The host faults the harness plants (host.PLANTED): the bundled skills turned back on for the one run, and the
# extensions left out, so the shell is gone.
PLANTS = {"bundled skills": lambda command: ["env", "GOOSE_BUILTIN_SKILLS=true"] + command,
          "no commands": _without_extensions}


def events(stdout):
    """The JSON events on stdout, one per line."""
    found = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            found.append(event)
    return found


def run_failure(stdout, returncode, timed_out):
    """Why the run failed, or None. goose prints an `error` event when the run fails and a `complete` event only
    when it ends well."""
    found = events(stdout)
    for event in reversed(found):
        if event.get("type") == "error":
            return f"host reported error: {event.get('error', '')}".rstrip(": ")
    if timed_out:
        return "timed out"
    if returncode not in (0, None):
        return f"exit code {returncode}"
    if not any(event.get("type") == "complete" for event in found):
        return "no complete event"
    return None


def action_log(stdout, home):
    return []  # read from the events in the next part


def tokens(stdout, home):
    return None  # read from the events in the next part


def request_logs(home):
    """The requests goose logged in the run's home: the first line of each log is the model's settings and the
    request it was sent, in the OpenAI chat format."""
    folder = Path(home) / ".local" / "state" / "goose" / "logs"
    found = []
    for path in sorted(folder.glob("llm_request.*.jsonl")) if folder.is_dir() else []:
        first = path.read_text(errors="replace").split("\n", 1)[0]
        try:
            record = json.loads(first)
        except json.JSONDecodeError:
            record = None
        found.append(record.get("input") if isinstance(record, dict) else None)
    return found


def exposure(stdout, home):
    """Every tool and every skill any logged request showed the model. None when goose logged no request, or one in
    another form, as no report is never 'nothing'. A skill row that does not parse is kept whole, so it is never a
    declared skill and stops the round."""
    requests, skills, tools = request_logs(home), set(), set()
    if not requests or len(requests) >= LOGS_KEPT:  # none, or perhaps not all of them
        return None
    for request in requests:
        if not isinstance(request, dict) or not isinstance(request.get("messages"), list):
            return None
        for tool in request.get("tools") or []:
            function = tool.get("function") if isinstance(tool, dict) else None
            name = function.get("name") if isinstance(function, dict) else None
            if not isinstance(name, str):
                return None
            tools.add(name)
        for message in request["messages"]:
            if isinstance(message, dict) and message.get("role") in ("system", "developer"):
                skills |= _skill_rows(_text(message.get("content")))
    return {"skills": sorted(skills), "tools": sorted(tools)}


def _text(content):
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return content if isinstance(content, str) else ""


def _skill_rows(text):
    """The skills of each skill part of a system prompt. One rule: a part starts at goose's `# Skills` heading followed
    by its opening sentence, and ends only where goose starts its next part, a blank line followed by a heading, or at
    the end of the prompt. Every other line in the part counts: a row `- name: description` is a skill, a blank line
    is nothing, and any other line, such as a description that runs onto more lines, is kept whole, so it is never a
    declared skill and stops the round."""
    skills, lines = set(), text.splitlines()
    for at, line in enumerate(lines):
        rest = [other for other in lines[at + 1:] if other.strip()]
        if line.strip() != SKILLS_HEADING or not rest or rest[0].strip() != SKILLS_OPENING:
            continue
        blank = False
        for row in lines[lines.index(rest[0], at + 1) + 1:]:
            if not row.strip():
                blank = True
                continue
            if blank and row.startswith("#"):
                break
            blank = False
            name, colon, _ = row[2:].partition(": ") if row.startswith("- ") else ("", "", "")
            skills.add(name if colon and name else row)
    return skills
