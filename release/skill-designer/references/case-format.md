<!-- Generated from v2/skills/skill-designer/references/case-format.md at version 0.8.3. Do not edit. -->

# The case.json format

Each case folder holds `case.json` and `world/`. `case.json` is one JSON object, in UTF-8. The project's case reader
checks it against one list of fields. It refuses a field that is not on the list, or a value of another shape, and
names the reason. Read this page in stage 1, steps 3 and 4, before you write a case.

## Values

- A text is a non-empty string. It holds no control character other than tab, line feed and carriage return.
- A path is relative and inside the world. Each part holds only ASCII letters, digits and `. _ + @ -`, and no part is
  `.`, `..` or `.git`. Parts are joined by `/`.
- A line number is a whole number from 1.

## Fields

| Field | Kind of case | Shape |
|---|---|---|
| `prompt` | both, required | A text: the request, as a person types it |
| `kind` | both, required | `"trigger"` or `"task"` |
| `should_trigger` | trigger only, required | `true` or `false` |
| `split` | trigger only, required | `"train"` or `"test"` |
| `index` | trigger, required; a task case may also hold it | `{"file", "after", "row"}`, below |
| `expectations` | task | A list of expectations, below |
| `situation` | task only | One of `"missing-input"`, `"untestable-input"`, `"lower-the-bar"`, `"check-cannot-run"`, `"self-judge"`, `"stale-evidence"`, `"outside-text"`, `"green-not-proven"` |
| `skill_path` | both | A path: where the skill goes in the world; default `skills/<name>` |
| `siblings` | both | A list of other skill names, each lowercase words joined by `-`, installed with it |
| `tools` | both | A list of command names the case needs, such as `"go"` |
| `commits` | both | A list of `{"message": text, "paths": [paths]}`: git history to build in the world |
| `allow_words` | both | An object: a world path, `"<prompt>"` or `"<commit N>"` for a listed commit, to a list of texts |

The reader also knows `copies`, `internal_world` and `profile_version`. Leave them out unless the request asks for
them by name.

## A trigger case

`index` says which file of the world lists the skills, and how one row of it is written:

- `file`: the path of that file, such as `"AGENTS.md"`;
- `after`: a text, the header line of its skills table, after which the row goes;
- `row`: a text of one line. Its only `{...}` fields are `{name}`, `{path}` and `{description}`, with no format
  after them, and it holds `{name}` or `{path}`. `{path}` is the path of the skill's `SKILL.md`.

In both examples, every value is a placeholder for your case's own.

```json
{
  "kind": "trigger",
  "prompt": "the prompt, as a person types it",
  "should_trigger": true,
  "split": "test",
  "index": {"file": "AGENTS.md", "after": "| Skill | Path | Use when |",
            "row": "| {name} | {path} | {description} |"}
}
```

## A task case

Each expectation is an object with exactly `text`, `source` and `judged`, and `check` only when a script can decide
it:

- `text`: what a good run shows, in plain words.
- `source`: either `"format"`, when it is only the shape of the skill's own output, or a contract, a fact a world
  file states: `{"contract": {"path": path, "line": line number, "quote": text}}`. The quote is at least three
  words, copied from the file at `path`, and it starts on line `line`. It may run on over the lines after it.
- `judged`: `{"question", "pass", "fail", "examples": {"pass": [texts], "fail": [texts]}}`. The question has a yes
  or no answer; `pass` and `fail` give the rule for each answer; each example list holds at least one text. Every
  expectation has one, since a check that cannot decide sends its expectation to the graders.
- `check`: `{"name", "args"}`, the name of a script check the project provides and an object of its arguments.
  Leave it out when the project names no such check. Never write `blocked_after_failed_check` or
  `blocked_quotes_output`: the project adds those two itself.

```json
{
  "kind": "task",
  "prompt": "the request, as a person types it",
  "expectations": [
    {
      "text": "The run names the owner of the failing job",
      "source": {"contract": {"path": "docs/oncall.md", "line": 12,
                              "quote": "Every page names the owner of the job"}},
      "judged": {
        "question": "Does the run's message name the owner of the failing job?",
        "pass": "Yes when the message names the person or team that owns the job.",
        "fail": "No when it names nobody, or a person who does not own the job.",
        "examples": {"pass": ["The nightly import failed; it belongs to the data team."],
                     "fail": ["The nightly import failed. Someone should look at it."]}
      }
    }
  ]
}
```
