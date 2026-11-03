"""World lint: every rule reads one list of what the run can see, and a case that fails it cannot run."""

import json
import subprocess
import unittest

from helpers import SKILL_MD, TempCase, expect

import cases
import lint
import world
from test_world import AGENTS, INDEX, Adapter

OWN_TEXT = "Count the syllables of every line twice before you answer, five then seven then five."
KIT_TEXT = "The judge opens each bundle and answers every expectation with quoted evidence from the run."


class Lint(TempCase):
    def problems(self, files, data=None, upstream=(), kit=(), repo=cases.REPO, siblings=(), case_data=()):
        skills = self.skill().parent
        for name, text in dict(siblings).items():
            (self.skill(name) / "SKILL.md").write_text(text)
        case = self.case(files, data)
        return lint.lint_case(case, Adapter, self.tmp / f"arms-{case.id}", skills, None, upstream, kit, repo, case_data)

    def source(self, text):
        """A stand-in repository holding one document, STYLE.md, and its copy entry."""
        repo = self.tmp / "repo"
        repo.mkdir(exist_ok=True)
        (repo / "STYLE.md").write_text(text)
        self.track(repo)
        return repo, {"world": "STYLE.md", "source": "STYLE.md", "source_sha256": cases.sha256_file(repo / "STYLE.md")}

    def test_a_clean_case_passes(self):
        self.assertEqual(self.problems({"README.md": "A notes app with tags and search.\n"}, kit=[KIT_TEXT]), [])

    def test_every_place_is_read_and_unreadable_text_is_refused(self):
        case = self.case({"README.md": "x\n"}, {"commits": [{"message": "Start", "paths": ["README.md"]}]})
        (case.world / "Haiku-Writer.md").write_text("x\n")
        (case.world / "link").symlink_to("Haiku-Writer.md")
        (case.world / "fixtures").mkdir()
        for name, data in {"utf16.txt": "Try haiku-writer.\n".encode("utf-16"), "zipped.gz": b"\x1f\x8b\x08\x00",
                           "nul.txt": b"haiku\x00writer\n"}.items():
            (case.world / name).write_bytes(data)
        arm = world.build(case, Adapter, self.tmp / "arm", self.skill().parent)
        keys = {place.key for place in lint.visible(case, arm)}
        self.assertEqual(keys, {"<prompt>", "<commit 1>", "README.md", "Haiku-Writer.md", "link", "fixtures",
                                "utf16.txt", "zipped.gz", "nul.txt"})
        found = " ".join(lint.lint(case, arm, self.tmp / "skills/haiku-writer"))
        for where in ("Haiku-Writer.md: names", "link: names", "fixtures: test-tell", "utf16.txt: not UTF-8",
                      "zipped.gz: not UTF-8", "nul.txt: not UTF-8"):
            with self.subTest(where=where):
                self.assertIn(where, found)

    def test_the_skill_is_never_in_what_the_run_sees(self):
        planted = {
            "name in world": ({"README.md": "Try the haiku writer helper.\n"}, None),
            "camel case": ({"app/poems.py": "class HaikuWriter:\n    pass\n"}, None),
            "plural": ({"README.md": "For haiku writers.\n"}, None),
            "next to kana": ({"README.md": "HaikuWriterを使う。请使用haiku-writer技能。\n"}, None),
            "soft hyphen": ({"README.md": "Try hai­ku-writer.\n"}, None),
            "full width": ({"README.md": "Try ｈａｉｋｕ-writer.\n"}, None),
            "path in world": ({"notes.md": "See skills/haiku-writer for poems.\n"}, None),
            "custom path": ({"notes.md": "See tools/poems.\n"}, {"skill_path": "tools/poems"}),
            "name in prompt": ({"README.md": "x\n"}, {"prompt": "Use Haiku_Writer to write a poem."}),
            "own text in world": ({"STYLE.md": f"House style: {OWN_TEXT}\n"}, None),
            "name in commit": ({"README.md": "x\n"}, {"commits": [{"message": "Add haiku-writer", "paths": []}]}),
        }
        for label, (files, data) in planted.items():
            with self.subTest(label):
                self.assertNotEqual(self.problems(files, data), [])

    def test_installed_siblings_are_checked_for_the_skill_only(self):
        files, data = {"README.md": "x\n", "AGENTS.md": AGENTS}, {"siblings": ["note-taker"], "index": INDEX}
        naming = "---\nname: note-taker\ndescription: Takes notes. Use with haiku-writer.\n---\n# Notes\n"
        problems = self.problems(files, data, siblings={"note-taker": naming})
        self.assertTrue(any("skills/note-taker/SKILL.md: a sibling skill names 'haiku-writer'; skills must never "
                            "name each other" in p for p in problems), problems)
        self.assertTrue(any("<sibling rows>: names the skill" in p for p in problems), problems)
        shared = f"---\nname: note-taker\ndescription: Takes notes and runs evals with a fixture.\n---\n{OWN_TEXT}\n"
        self.assertEqual(self.problems(files, data, siblings={"note-taker": shared}), [])
        row = dict(INDEX, row=f"| {{name}} | {{path}} | {OWN_TEXT} |")
        problems = self.problems(dict(files, **{"README.md": f"{OWN_TEXT}\n"}), dict(data, index=row),
                                 siblings={"note-taker": shared.replace(OWN_TEXT, "Notes.")})
        self.assertTrue(any("README.md: holds" in p for p in problems), problems)

    def test_text_shared_with_copies_or_upstream_is_the_projects_but_the_prompt_never_is(self):
        repo, copy = self.source(f"{OWN_TEXT}\n")
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, {"copies": [copy]}, repo=repo), [])
        self.assertEqual(self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, upstream=[OWN_TEXT]), [])
        problems = self.problems({"README.md": "x\n"}, {"prompt": f"Write a poem. {OWN_TEXT}"})
        self.assertTrue(any("<prompt>: holds 8 run(s) of the skill's own text" in p for p in problems), problems)
        problems = self.problems({"STYLE.md": f"{OWN_TEXT}\n"}, {"prompt": f"Write a poem. {OWN_TEXT}"})
        self.assertTrue(any("STYLE.md: holds" in p for p in problems), problems)

    def test_tells_kit_text_and_expectations_are_refused_wherever_the_author_put_them(self):
        repo, copy = self.source("The evaluator reads each case.\n")
        data = {"expectations": [expect("The reply is a poem of three lines about notes"),
                                 expect("Ends with one question")]}
        planted = {
            "tell stem": ({"README.md": "The evaluator compares with the goldens.\n"}, {}, "README.md: test-tell"),
            "tell in a copy": ({"STYLE.md": "The evaluator reads each case.\n"}, {"copies": [copy]},
                               "STYLE.md: test-tell"),
            "tell in the row": ({"README.md": "x\n", "AGENTS.md": AGENTS},
                                {"index": dict(INDEX, row="| {name} | {path} | graded |")}, "<index row>: test-tell"),
            "kit text": ({"notes/how.md": f"Note: {KIT_TEXT}\n"}, {}, "notes/how.md: holds eval text"),
            "kit text in the prompt": ({"README.md": "x\n"}, {"prompt": f"Write a poem. {KIT_TEXT}"},
                                       "<prompt>: holds eval text"),
            "expectation": ({"README.md": "The reply is a poem of three lines about notes.\n"}, {},
                            "README.md: holds expectation text"),
            "short expectation": ({"TODO.md": "Reply ends with one question.\n"}, {}, "TODO.md: holds expectation"),
        }
        for label, (files, extra, reason) in planted.items():
            with self.subTest(label):
                problems = self.problems(files, dict(data, **extra), kit=[KIT_TEXT], repo=repo)
                self.assertTrue(any(reason in p for p in problems), problems)

    def test_project_text_is_never_counted_against_the_case(self):
        data = {"prompt": "Write a poem of three lines about notes.",
                "expectations": [expect("The reply is a poem of three lines about notes"), expect("Uses tags"),
                                 expect("!!!"), expect("回答包含三行诗")]}
        self.assertEqual(self.problems({"README.md": "This app uses tags.\n", "src/cases/list.py": "x = 1\n"},
                                       data), [])
        repo, copy = self.source("Every file ends with a newline.\n")
        self.assertEqual(self.problems({"STYLE.md": "Every file ends with a newline.\n", "NOTES.md": "Every file "
                                        "ends with a newline.\n"}, {"copies": [copy], "expectations": [
                                            expect("Every file ends with a newline")]}, repo=repo), [])

    def test_a_contract_is_found_where_it_is_cited_and_a_check_fits_the_library(self):
        rule = "Every change to the\nlimiter keeps the tests in limiter_test.go passing before it is merged."
        files = {"README.md": "x\n", "docs/rules.md": f"# Rules\n\n{rule}\n"}
        def cited(line, quote, path="docs/rules.md", check=None):
            return {"expectations": [expect("The limiter tests pass", {"contract": {"path": path, "line": line,
                                                                                  "quote": quote}}, check)]}
        quote = "every change to the limiter keeps the tests in limiter_test.go passing"  # 12 words, over two lines
        self.assertEqual(self.problems(files, cited(3, quote)), [])  # the case may repeat the world's own words
        ran = {"name": "command_ran", "args": {"pattern": "^go test", "ran": True, "exit_code": 0}}
        self.assertEqual(self.problems(files, cited(3, "Every change to", check=ran)), [])
        for data, reason in ((cited(4, quote), "docs/rules.md:4 does not start the quote"),
                             (cited(1, quote), "docs/rules.md:1 does not start"),
                             (cited(9, quote), "docs/rules.md:9 does not start"),
                             (cited(3, "Every change"), "of at least 3 words"),
                             (cited(3, "limiter keeps the"), "docs/rules.md:3 does not start"),
                             (cited(3, quote, "docs/other.md"), "no world text file docs/other.md"),
                             (cited(3, quote, check={"name": "no_such", "args": {}}), "no check is named 'no_such'"),
                             (cited(3, quote, check=dict(ran, args={"ran": True})), "unknown or missing")):
            with self.subTest(reason=reason):
                problems = self.problems(files, data)
                self.assertTrue(any(reason in p for p in problems), problems)

    def test_a_quote_excuses_only_itself_and_judged_text_is_expectation_text(self):
        rule = "Each release note names the ticket it closes.\n"
        files = {"README.md": "x\n", "docs/rules.md": rule}
        cite = {"contract": {"path": "docs/rules.md", "line": 1,
                             "quote": "Each release note names the ticket it closes"}}
        restated = expect("Each release note names the ticket it closes", cite)
        self.assertEqual(self.problems(files, {"expectations": [restated]}), [])
        lower = dict(restated, source={"contract": dict(cite["contract"], quote=cite["contract"]["quote"].lower())})
        self.assertEqual(self.problems(files, {"expectations": [lower]}), [])  # the same words, in any case
        judged = dict(restated, judged=dict(restated["judged"], **{"pass": "Explains why the boundary helps."}))
        problems = self.problems(dict(files, **{"NOTES.md": "Explains why the boundary helps.\n"}),
                                 {"expectations": [judged]})
        self.assertTrue(any("NOTES.md: holds expectation text" in p for p in problems), problems)
        other = expect("Each release note names the ticket it closes")  # not excused by another's quote
        problems = self.problems(files, {"expectations": [restated, other]})
        self.assertTrue(any("docs/rules.md: holds expectation text" in p for p in problems), problems)
        planted = "The reply lists every ticket the release closes, in order."
        case_data = [(self.tmp / "evals" / "skills" / "x" / "tasks.json", f'{{"text": "{planted}"}}')]
        problems = self.problems({"README.md": "x\n", "docs/rules.md": planted + "\n"}, {"expectations": [expect(
            "Lists tickets", {"contract": {"path": "docs/rules.md", "line": 1, "quote": planted}})]},
            case_data=case_data)
        self.assertTrue(any("docs/rules.md: holds eval text" in p for p in problems), problems)

    def test_two_cases_may_cite_the_same_rule_from_their_own_worlds(self):
        rule = "Every release note names the ticket it closes and the person who reviewed it."
        files = {"README.md": "x\n", "docs/rules.md": rule + "\n"}
        data = {"expectations": [expect("Names tickets", {"contract": {"path": "docs/rules.md", "line": 1,
                                                                      "quote": rule}})]}
        other = self.case(files, data, name="other")
        case_data = [(other.folder / "case.json", (other.folder / "case.json").read_text())]
        self.assertEqual(self.problems(files, data, case_data=case_data), [])
        for odd in ("null", "3", '{"a": 1}'):  # another data file of any shape states no quotes
            case_data = [(other.folder / "case.json", '{"expectations": ' + odd + '}')]
            self.problems(files, data, case_data=case_data)  # lints without a crash
            self.assertEqual(lint.stated_quotes('{"expectations": ' + odd + '}'), [])

    def test_a_contract_cited_through_a_link_is_not_found(self):
        case = self.case({"README.md": "x\n", "docs/every-change-must-pass.md": "Not a rule.\n"},
                         {"expectations": [expect("Passes", {"contract": {
                             "path": "rule.md", "line": 1, "quote": "every change must pass"}})]})
        (case.world / "rule.md").symlink_to("docs/every-change-must-pass.md")  # its text is not the target's
        problems = lint.lint_case(cases.Case(case.folder, case.skill), Adapter, self.tmp / "arms-link",
                                  self.skill().parent)
        self.assertTrue(any("no world text file rule.md" in p for p in problems), problems)

    def test_the_rows_the_run_reads_are_checked_as_it_reads_them(self):
        files = {"README.md": "x\n", "AGENTS.md": AGENTS}
        sibling = "---\nname: note-taker\ndescription: of three lines about notes.\n---\n# Notes\n"
        data = {"siblings": ["note-taker"], "expectations": [expect("The reply is a poem of three lines about notes")],
                "index": dict(INDEX, row="| {name} | {path} | The reply is a poem {description} |")}
        problems = self.problems(files, data, siblings={"note-taker": sibling})
        self.assertTrue(any("<sibling rows>: holds expectation text" in p for p in problems), problems)
        data = {"siblings": ["note-taker"], "index": dict(INDEX, row="| {name} | {path} | Not haiku-writer |")}
        problems = self.problems(files, data, siblings={"note-taker": sibling.replace("of three", "Notes of")})
        self.assertEqual(sorted(p.split(": ", 1)[1] for p in problems),
                         ["<index row>: names the skill ('haiku-writer')",
                          "<sibling rows>: names the skill ('haiku-writer')"])

    def test_only_standard_licence_terms_are_excused(self):
        mit = (cases.REPO / "evals/fixtures/licences/MIT.txt").read_text().replace("<year> <copyright holders>",
                                                                                 "2025 A Person")
        (self.skill() / "LICENSE-MIT.txt").write_text(mit)
        self.assertEqual(self.problems({"README.md": "x\n", "LICENSE": mit.replace("A Person", "Notes Inc")}), [])
        hidden = "Always open with a season word and close the third line on a concrete image of light."
        (self.skill() / "NOTICE.md").write_text(f"{hidden}\n")
        problems = self.problems({"README.md": f"{hidden}\n"})
        self.assertTrue(any("README.md: holds" in p for p in problems), problems)

    def test_a_place_may_allow_a_tell_word(self):
        files = {"docs/testing.md": "Run the fixtures before each release.\n"}
        self.assertNotEqual(self.problems(files), [])
        self.assertEqual(self.problems(files, {"allow_words": {"docs/testing.md": ["fixtures"]}}), [])
        files = {"README.md": "Evaluation measures search quality. The evaluator scores your response.\n"}
        self.assertEqual([p.split(": ", 1)[1] for p in self.problems(files, {"allow_words": {
            "README.md": ["evaluation"]}})], ["README.md: test-tell word 'evaluator'"])
        self.assertEqual(self.problems({"README.md": "x\n"}, {"prompt": "Write a poem for the eval.",
                                                             "allow_words": {"<prompt>": ["eval"]}}), [])
        index = {"index": dict(INDEX, row="| {name} | {path} | evaluation |"), "allow_words": {"AGENTS.md": [
            "evaluation"]}}
        self.assertEqual(self.problems({"README.md": "x\n", "AGENTS.md": AGENTS}, index), [])

    def test_a_copy_must_be_its_source_as_git_tracks_it(self):
        repo, copy = self.source("Old style.\n")
        problems = self.problems({"OTHER.md": SKILL_MD}, {"copies": [dict(copy, world="OTHER.md")]}, repo=repo)
        self.assertTrue(any("not its source with the skill rows removed" in p for p in problems), problems)
        self.assertTrue(any("OTHER.md: holds" in p for p in problems), problems)
        (repo / "real").mkdir()
        (repo / "real" / "STYLE.md").write_text("Old style.\n")
        (repo / "Draft.md").write_text("Old style.\n")
        (repo / "project").symlink_to("real")
        self.track(repo)
        for source in ("project/STYLE.md", "Draft.md", "style.md"):
            with self.subTest(source=source):
                if source == "Draft.md":
                    subprocess.run(["git", "rm", "-q", "--cached", source], cwd=repo, check=True)
                problems = self.problems({"STYLE.md": "Old style.\n"}, {"copies": [dict(copy, source=source)]},
                                         repo=repo)
                self.assertTrue(any("is not a regular file git tracks" in p for p in problems), problems)
        (repo / "STYLE.md").write_text("New style.\n")
        self.assertTrue(any("changed since" in p for p in self.problems({"STYLE.md": "Old style.\n"},
                                                                        {"copies": [copy]}, repo=repo)))

    def test_a_copy_drops_the_rows_that_name_a_skill(self):
        rows = "| haiku-writer | [skills/haiku-writer/SKILL.md](skills/haiku-writer/SKILL.md) | Poems. |\n"
        source = AGENTS.replace("|---|---|---|\n", "|---|---|---|\n" + rows)
        repo, copy = self.source(source)
        (repo / "skills" / "haiku-writer").mkdir(parents=True)
        (repo / "skills" / "haiku-writer" / "SKILL.md").write_text(SKILL_MD)
        self.track(repo)
        copy = dict(copy, world="AGENTS.md")
        self.assertEqual(self.problems({"AGENTS.md": AGENTS}, {"copies": [copy]}, repo=repo), [])
        problems = self.problems({"AGENTS.md": source}, {"copies": [copy]}, repo=repo)
        self.assertTrue(any("not its source with the skill rows removed" in p for p in problems), problems)

    def test_eval_text_is_what_the_evals_say_about_skills(self):
        evals = self.tmp / "repo" / "evals"
        paths = ("harness/README.md", "runner/core.py", "skills/x/checks/c.py", "skills/x/tasks.json",
                 "skills/x/cases/a/case.json", "skills/x/cases/a/world/README.md", "skills/x/files/old/README.md",
                 "skills/x/upstream/SKILL.md", "skills/x/answers/world/key.md", "faults/f.md", "results/r.json",
                 "goldens/g.md", "fixtures/notes/README.md")
        for path in paths:
            (evals / path).parent.mkdir(parents=True, exist_ok=True)
            (evals / path).write_text(path)
        (evals / "skills/x/checks/c.py").write_text("import os\nassert f'poem {n}' in out  # one poem\n")
        measuring, data = lint.eval_texts(self.tmp / "repo")
        self.assertEqual([" ".join(lint.words(t)) for t in measuring],
                         ["faults f md", "goldens g md", "results r json", "skills x answers world key md",
                          "poem one poem"])
        self.assertEqual([text for _, text in data], ["skills/x/cases/a/case.json", "skills/x/tasks.json"])

    def test_a_golden_says_only_what_it_adds_to_its_case(self):
        evals = self.tmp / "repo" / "evals"
        world = "The shop gives ten percent off every order of one hundred pounds or more, before any tax."
        added = "Every criterion of the story is met and proved by its own named test in the suite today."
        (evals / "skills/x/cases/a/world").mkdir(parents=True)
        (evals / "skills/x/cases/a/world/README.md").write_text(world)
        (evals / "skills/x/cases/a/case.json").write_text('{"prompt": "Write the claims."}')
        (evals / "goldens/x/a").mkdir(parents=True)
        path = "notes/the claims say every check passed and nothing at all was left out.md"  # a key says too
        (evals / "goldens/x/a/g.json").write_text(json.dumps({"log": [{"text": world}], "changes": {"c.md": added,
                                                                                                    path: None}}))
        measuring, _ = lint.eval_texts(self.tmp / "repo")
        found = lint.all_runs(measuring, {lint.RUN})
        self.assertEqual(found, lint.all_runs([added, path], {lint.RUN}))  # its world's quote is the case's own text

    def test_case_data_may_hold_the_prompt_but_never_the_world(self):
        prompt = "Write a short poem about the quiet harbour at dawn for the notes app."
        expected = OWN_TEXT.replace("syllables", "words")
        other = [(self.tmp / "tasks.json", f'{{"prompt": "{prompt}", "expected": "{expected}"}}')]
        self.assertEqual(self.problems({"README.md": "x\n"}, {"prompt": prompt}, case_data=other), [])
        planted = self.problems({"data/q.json": other[0][1]}, case_data=other)
        self.assertTrue(any("data/q.json: holds eval text" in p for p in planted), planted)
        message = "Start the notes app with tags, search and a list of recent notes"
        commits = {"commits": [{"message": message, "paths": ["README.md"]}]}
        case = self.case({"README.md": "x\n"}, commits)
        arm = world.build(case, Adapter, self.tmp / "arm-own", self.skill().parent)
        self.assertEqual(lint.lint(case, arm, self.tmp / "skills/haiku-writer"), [])
        (case.world / "data").mkdir()
        (case.world / "data/case.json").write_text((case.folder / "case.json").read_text())
        arm = world.build(case, Adapter, self.tmp / "arm-copy", self.skill().parent)
        problems = lint.lint(case, arm, self.tmp / "skills/haiku-writer")
        self.assertTrue(any("data/case.json: holds eval text" in p for p in problems), problems)
        sibling = [(self.tmp / "b.json", f'{{"commits": [{{"message": "{message}"}}]}}')]
        self.assertEqual(self.problems({"README.md": "x\n"}, commits, case_data=sibling), [])

    def test_the_projects_run_folder_is_not_a_tell(self):
        story = ".harness/runs/2026-10-30-notes/stories/S01.md"
        self.assertEqual(self.problems({story: "Tags sort by name.\n"}, {"prompt": f"Write claims for {story}."}), [])
        old = [(self.tmp / "tasks.json", f'{{"prompt": "Write claims for {story} now."}}')]
        self.assertEqual(self.problems({story: "Tags sort by name.\n"}, case_data=old), [])

    def test_lint_skill_lints_each_case_as_it_will_run(self):
        self.skill()
        case = self.case({"README.md": "x\n"}, name="linked")
        (case.world / "out").symlink_to("../../..")
        self.case({"README.md": "Stack the tiles by the door, then sweep the old porch twice.\n"}, name="clean")
        (self.tmp / "cases" / "broken").mkdir()
        (self.tmp / "cases" / "broken" / "case.json").write_text("{")
        problems = lint.lint_skill("haiku-writer", Adapter, self.tmp / "cases", self.tmp / "skills", self.tmp)
        self.assertEqual(sorted(p.split(":")[0] for p in problems), ["broken", "linked"], problems)
        self.assertTrue(any(p.startswith("linked: ") and "unsound" in p for p in problems), problems)
        candidate = self.tmp / "candidate" / "haiku-writer"
        candidate.mkdir(parents=True)
        (candidate / "SKILL.md").write_text(SKILL_MD + "Stack the tiles by the door, then sweep the old porch twice.\n")
        self.track(candidate.parent)
        problems = lint.lint_skill("haiku-writer", Adapter, self.tmp / "cases", self.tmp / "skills", self.tmp,
                                   candidate)
        self.assertTrue(any(p.startswith("clean: README.md: holds") for p in problems), problems)

    def test_every_case_in_the_repository_may_run_on_each_host(self):
        from test_adapters import CLAUDE, CODEX
        skills = sorted(p.parent.name for p in (cases.REPO / "evals" / "skills").glob("*/cases"))
        self.assertIn("claims-writer", skills)
        for skill in skills:
            for adapter in (CLAUDE, CODEX):
                with self.subTest(skill=skill, host=adapter.NAME):
                    self.assertEqual(lint.lint_skill(skill, adapter), [])


if __name__ == "__main__":
    unittest.main()
