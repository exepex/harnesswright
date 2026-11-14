# goose fixtures

Four real goose runs, used by `test_goose_events.py` to test the goose adapter's event readers. Each was run on
2026-11-14 through `host.run`, in the jail and behind the gate, with the patched goose 1.59.1 (`adapters/goose`), the
owner's OpenRouter key and one model. Each world held `notes.txt` (`pear`, `apple`, `fig`), a `README.md` whose first
line is `# Sample`, and one skill, `tidy`, which sorts `notes.txt` into `tidy.txt`.

| Run | Mode | Prompt, in short | What it shows |
|---|---|---|---|
| `full` | task | Use the tidy skill; run `wc -l tidy.txt` and `cat missing.txt`; edit `tidy.txt`; use the tree tool; delegate `head -1 README.md` to a sub-agent | A skill load, commands with exit codes 0 and 1, a write, an edit, a read, a sub-agent and its command |
| `parallel` | task | Call delegate twice in one turn | Two sub-agents at once, each request logged |
| `blocked` | trigger | Write `hello.txt`, then run `ls` | A write the jail refused (read-only world) |
| `error` | task | Reply with one word, with an unknown model | An `error` event and no usage |

## What each holds

- `store.json`: goose's session store, `sessions.db`, as rows of the three tables the adapter reads: `sessions`
  (id, working folder), `messages` (session, role, content) in stored order, and `usage_ledger` (model, input,
  cache read, cache write, output). The test builds a SQLite file from them.
- `logs/`: the request logs goose wrote, each cut to its request line and its usage or error line.
- `stdout.jsonl`: the `error` and `complete` events goose printed.

## How they were made

1. The run's own scrub (`scrub.Scrub.of_run`) went over every file, as `evidence.reported` does for every run, so
   credentials are redacted and the run's folders show as neutral words (`/run/project` is the world). Each run also
   passed `evidence.reported` itself, which found no canary.
2. Model ids were replaced by neutral words (`model-a`, `model-x`, AGENTS.md). The unknown-model error listed every
   model OpenRouter offers; that list was left out.
3. Only what the adapter never reads was left out: the thinking text of each stored message, the streamed text
   chunks in the logs and on stdout, every message of a logged request but its system prompt, and every field of a
   logged tool but its name.

The capture and cut scripts are not part of the kit; they are kept with the review notes of this change (project files, `reviews/o1b/capture/`).
