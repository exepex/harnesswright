"""One setup (doc 12): a round's setup has one fingerprint, which leaves out the skill's own hash; two results
compare only when their fingerprints match, else they are not comparable and the changed parts are named; and a
plan for a skill changed since its verified version must run that version as `previous`."""

import contextlib
import io
import json
import shutil
import tarfile
import types
from unittest import mock

import test_results
from helpers import TempCase
from test_rounds import stub
from test_runs import VERSION, Round

import results
import rounds
import setups
from cases import REPO, Case

HOST = {"label": "verified", "model": "named-model", "runs": {"c1, with_skill": 3}}
DRIFT = {"fakehost": {"tools": {"fakehost": {"version": "fakehost 1.0"}, "jq": {"version": "jq-1.6"}},
                      "own files": {"task": [], "trigger": []}}}
TOOL = types.SimpleNamespace(siblings=[], tools=["jq"])  # a case that declares a tool and no sibling


class Fingerprints(Round):
    def setup(self, record, cases=None, drift=DRIFT, *folder):
        return setups.setup(record, "haiku-writer", cases or {"c1": Case(self.case_dir, "haiku-writer")}, drift,
                            *folder)

    def test_the_fingerprint_leaves_out_the_skill_and_its_previous_version(self):
        record = self.plan()
        first = self.setup(record)
        self.assertEqual(len(first["fingerprint"]), 64)
        self.assertNotIn(record["skills"]["haiku-writer"]["sha256"], json.dumps(first["parts"]))
        changed = json.loads(json.dumps(record))
        changed["skills"]["haiku-writer"]["sha256"] = "f" * 64
        changed["previous"] = {"haiku-writer": {"commit": "a" * 40, "path": "skills/haiku-writer", "sha256": "e" * 64}}
        self.assertEqual(self.setup(changed), first)

    def test_each_part_of_the_setup_that_changes_is_named(self):
        record = self.plan()
        first = self.setup(record)
        for part, change in {
                "kit": lambda r: r.update(kit="0" * 64),
                "cases": lambda r: r["cases"]["haiku-writer"].update(c1="0" * 64),
                "adapters": lambda r: r["adapters"].update(fakehost="0" * 64),
                "hosts": lambda r: r["hosts"]["fakehost"].update(model="other-model"),
                "runs": lambda r: r["plan"].update(runs=5),
                "pinned": lambda r: r.pop("pinned")}.items():
            with self.subTest(part):
                changed = json.loads(json.dumps(record))
                change(changed)
                after = self.setup(changed)
                self.assertNotEqual(after["fingerprint"], first["fingerprint"])
                self.assertEqual(setups.changed(first, after), [part])
        self.assertEqual(setups.changed(first, self.setup(record, drift={})), ["graders", "tools"])

    def test_only_the_skill_s_own_siblings_and_tools_are_parts(self):
        record = self.plan()
        record["skills"]["limerick-writer"] = {"sha256": "1" * 64, "source": None, "upstream": None}
        first = self.setup(record)  # another skill installed in the round is no part of this one's setup
        self.assertEqual((first["parts"]["siblings"], first["parts"]["tools"]), ({}, {"fakehost": {}}))
        changed = json.loads(json.dumps(record))
        changed["skills"]["limerick-writer"]["sha256"] = "2" * 64
        self.assertEqual(self.setup(changed), first)
        declares = {"c1": types.SimpleNamespace(siblings=["limerick-writer"], tools=[])}
        self.assertEqual(self.setup(record, declares)["parts"]["siblings"],
                         {"limerick-writer": record["skills"]["limerick-writer"]})
        self.assertEqual(setups.changed(self.setup(record, declares), self.setup(changed, declares)), ["siblings"])
        tools = self.setup(record, {"c1": TOOL})
        self.assertEqual(tools["parts"]["tools"], {"fakehost": {"jq": {"version": "jq-1.6"}}})
        newer = json.loads(json.dumps(DRIFT))
        newer["fakehost"]["tools"]["jq"] = {"version": "jq-1.7"}
        self.assertEqual(setups.changed(tools, self.setup(record, {"c1": TOOL}, newer)), ["tools"])
        drifted = {"fakehost": {**DRIFT["fakehost"], "own files": {"task": ["world/.state"], "trigger": []}}}
        self.assertEqual(self.setup(record, {"c1": TOOL}, drifted), tools)  # own files may differ by name only

    def test_a_changed_label_rule_changes_the_fingerprint(self):
        record = self.plan()
        folder = self.tmp / "harness"
        shutil.copytree(setups.HARNESS, folder, ignore=shutil.ignore_patterns("__pycache__", "tests"))
        first = self.setup(record, None, DRIFT, folder)
        self.assertEqual(first, self.setup(record))  # the same code, the same setup
        with open(folder / "labels.py", "a") as handle:
            handle.write("# a changed rule\n")
        self.assertEqual(setups.changed(first, self.setup(record, None, DRIFT, folder)),
                         ["label rule"])


class RealRepository(TempCase):
    def test_a_skill_planned_alone_or_beside_another_has_one_fingerprint(self):
        def fingerprint(skills):
            path = self.tmp / "plan.json"
            path.write_text(json.dumps({"round": "real", "skills": skills, "runs": 3,
                                        "hosts": [{"adapter": "claude-code", "model": "m1"}]}))
            record = rounds.plan(path, version=stub, at=lambda repo: "0" * 40)  # this tree may hold work in progress
            own = {i: Case(REPO / "evals" / "skills" / "skill-designer" / "cases" / i, "skill-designer")
                   for i in skills["skill-designer"]}
            return setups.setup(record, "skill-designer", own, {"claude-code": {"tools": {}}})["fingerprint"]
        designer = sorted(p.name for p in (REPO / "evals" / "skills" / "skill-designer" / "cases").iterdir())
        writer = sorted(p.name for p in (REPO / "evals" / "skills" / "claims-writer" / "cases").iterdir())
        self.assertEqual(fingerprint({"skill-designer": designer}),
                         fingerprint({"skill-designer": designer, "claims-writer": writer}))


class Planned(Round):
    def results_file(self, sha256, label="verified"):
        entry = {"round": "r0", "reference": "fakehost", "ran": ["fakehost"], "hosts": {"fakehost": {"label": label}}}
        if sha256 is not None:
            entry["skill_sha256"] = sha256
        folder = self.repo / "evals" / "results"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "haiku-writer.json").write_text(json.dumps({"skill": "haiku-writer", "rounds": [entry]}))

    def test_a_skill_changed_since_its_verified_version_must_run_it_as_previous(self):
        record = self.plan()
        old, sha256 = self.git("rev-parse", "HEAD"), record["skills"]["haiku-writer"]["sha256"]
        self.results_file(sha256)
        (self.repo / "skills" / "haiku-writer" / "SKILL.md").write_text(
            "---\nname: haiku-writer\ndescription: Writes a better haiku. Use when asked for a haiku.\n---\n")
        with self.assertRaisesRegex(rounds.RoundError, f"haiku-writer was verified in round r0 with hash {sha256}, "
                                                       "and it has changed since"):
            self.plan()
        record = self.plan(previous={"haiku-writer": old})
        self.assertEqual(record["verified"], {"haiku-writer": {"round": "r0", "sha256": sha256}})
        self.assertEqual(record["previous"]["haiku-writer"]["sha256"], sha256)

    def test_an_unchanged_skill_runs_no_previous_arm_and_stands_alone(self):
        sha256 = self.plan()["skills"]["haiku-writer"]["sha256"]
        self.results_file(sha256)
        record = self.plan()
        self.assertEqual((record["previous"], record["verified"]),
                         ({}, {"haiku-writer": {"round": "r0", "sha256": sha256}}))

    def test_an_entry_with_no_skill_hash_is_unknown_and_never_guessed(self):
        self.plan()
        self.results_file(None)
        record = self.plan()
        self.assertEqual(record["verified"]["haiku-writer"], {
            "round": "r0", "sha256": None, "unknown": "the entry was written before results recorded the skill's hash"})

    def test_a_skill_run_in_trigger_cases_only_needs_no_previous(self):
        sha256 = self.plan()["skills"]["haiku-writer"]["sha256"]
        self.results_file(sha256)
        trigger = self.case_dir.parent / "t1"
        (trigger / "world").mkdir(parents=True)
        (trigger / "world" / "AGENTS.md").write_text("| Skill | Path | Use when |\n|---|---|---|\n")
        index = {"file": "AGENTS.md", "after": "|---|---|---|", "row": "| {name} | [{path}]({path}) | {description} |"}
        (trigger / "case.json").write_text(json.dumps({"prompt": "Write a haiku.", "kind": "trigger",
                                                       "should_trigger": True, "split": "test", "index": index}))
        other = self.repo / "skills" / "limerick-writer"  # a held skill whose task case the faults are planted on
        other.mkdir()
        (other / "SKILL.md").write_text("---\nname: limerick-writer\ndescription: Writes a limerick. Use when asked "
                                        "for a limerick.\n---\n")
        shutil.copytree(self.case_dir, self.repo / "evals" / "skills" / "limerick-writer" / "cases" / "l1")
        (self.repo / "skills" / "haiku-writer" / "SKILL.md").write_text(
            "---\nname: haiku-writer\ndescription: Writes a better haiku. Use when asked for a haiku.\n---\n")
        fault = {"fault_case": {"skill": "limerick-writer", "case": "l1"}}
        with self.assertRaisesRegex(rounds.RoundError, "it has changed since"):
            self.plan(fault_case=fault["fault_case"])  # its task case asks for the verified version
        path = self.tmp / "plan.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "skills": {"haiku-writer": ["t1"]}, **fault}))
        record = rounds.plan(path, repo=self.repo, adapters=self.repo / "adapters", version=lambda m, **c: VERSION)
        self.assertEqual((record["previous"], record["verified"]),
                         ({}, {"haiku-writer": {"round": "r0", "sha256": sha256}}))  # trigger cases compare none

    def test_only_a_verified_reference_label_is_a_verified_version(self):
        self.plan()
        self.results_file("f" * 64, label="inconclusive")
        self.assertEqual(self.plan()["verified"], {})


class Compared(TempCase):
    round = test_results.Results.round  # its helper only, not its tests

    def setup_round(self, name, setup):
        """A finished round whose label file records `setup` for the skill."""
        folder, archive = self.round(name, skills={"haiku-writer": {"fakehost": HOST}})
        labels = folder / "labels" / "t1.json"
        labels.write_text(json.dumps({**json.loads(labels.read_text()), "setups": {"haiku-writer": setup}}))
        manifest = folder / "manifest.json"
        manifest.write_text(json.dumps({**json.loads(manifest.read_text()),
                                        "skills": {"haiku-writer": {"sha256": "d" * 64}}}))
        archive.unlink()
        with tarfile.open(archive, "w") as tar:
            tar.add(folder, arcname=name)
        return folder, archive

    def setup_of(self, **parts):
        whole = {"kit": "a" * 64, "hosts": {"fakehost": {"model": "named-model"}}, "label rule": "b" * 64, **parts}
        return {"parts": whole, "fingerprint": json.dumps(whole, sort_keys=True)}

    def test_the_results_entry_records_the_skill_s_hash_and_its_setup(self):
        setup = self.setup_of()
        entry = results.entries(*self.setup_round("r1", setup))["haiku-writer"]
        self.assertEqual((entry["skill_sha256"], entry["previous_sha256"], entry["setup"]), ("d" * 64, None, setup))

    def test_rounds_compare_only_on_the_same_setup_and_name_what_changed(self):
        old = {"round": "r1", "hosts": {}}  # written before setups were recorded
        same, other = self.setup_of(), self.setup_of(kit="c" * 64, **{"label rule": "e" * 64})
        found = results.compared([old, {"round": "r2", "setup": same}, {"round": "r3", "setup": same},
                                  {"round": "r4", "setup": other}])
        self.assertEqual(found, ["r2 beside r1: unknown: r1 recorded no setup", "r3 beside r2: same setup",
                                 "r4 beside r3: not comparable: setup changed: kit, label rule"])

    def test_rounds_py_results_writes_and_prints_not_comparable_naming_the_change(self):
        out = self.tmp / "repo" / "evals" / "results"
        out.mkdir(parents=True)
        self.setup_round("r1", self.setup_of())
        self.setup_round("r2", self.setup_of(hosts={"fakehost": {"model": "other-model"}}))
        printed = io.StringIO()
        with mock.patch.object(rounds, "REPO", self.tmp / "repo"), contextlib.redirect_stdout(printed):
            for name in ("r1", "r2"):
                self.assertEqual(rounds.main(["results", name, "--store", str(self.tmp / "store"),
                                              "--archive", str(self.tmp / f"{name}.tar")]), 0)
        line = "r2 beside r1: not comparable: setup changed: hosts"
        self.assertEqual(json.loads((out / "haiku-writer.json").read_text())["compared"], [line])
        self.assertEqual(printed.getvalue().splitlines()[-1], f"  {line}")
        self.assertEqual(results.verified(results.recorded(out, "haiku-writer")), {"round": "r2", "sha256": "d" * 64})

