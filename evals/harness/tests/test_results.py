"""Round results: a finished round's labels are copied whole into evals/results, named by its manifest, kit and
archive, and a round that did not finish, or whose kit or archive is not its own, is refused."""

import json
import tarfile

from helpers import TempCase

import labels
import results

KIT = "a" * 64
HOST = {"label": "verified", "lift": 0.5, "model": "named-model", "runs": {"c1, with_skill": 3}}
GATES = ["kit check", "lint", "probe", "faults", "run", "check", "grade", "label"]


class Results(TempCase):
    def round(self, name="r1", passed=True, approved=KIT, skills=None, ran=None, shipped=None):
        folder = self.tmp / "store" / name
        (folder / "attempts").mkdir(parents=True)
        (folder / "labels").mkdir()
        (folder / "manifest.json").write_text(json.dumps({"round": name, "kit": KIT}))
        outcomes = {"kit check": {"approved": approved}, "probe": {"passed": ran or ["fakehost"], "not run": {}}}
        gates = [{"gate": g, "passed": passed or g != "label", "outcome": outcomes.get(g, {})} for g in GATES]
        (folder / "attempts" / "t1.json").write_text(json.dumps({"gates": gates}))
        (folder / "labels" / "t1.json").write_text(json.dumps({
            "attempt": "t1", "commit": "c" * 40, "round": name, "reference": "fakehost", "prices": "2026-11-14",
            "thresholds": {"min_runs": 3}, "skills": skills or {"haiku-writer": {"fakehost": HOST}},
            **({"shipped": shipped} if shipped is not None else {})}))
        archive = self.tmp / f"{name}.tar"
        with tarfile.open(archive, "w") as tar:
            tar.add(folder, arcname=name)
        return folder, archive

    def test_a_finished_round_is_copied_whole_and_named_exactly(self):
        folder, archive = self.round()
        entry = results.entries(folder, archive)["haiku-writer"]
        self.assertEqual(entry["hosts"], {"fakehost": HOST})
        self.assertEqual((entry["round"], entry["attempt"], entry["kit"]), ("r1", "t1", KIT))
        self.assertEqual((entry["reference"], entry["prices"], entry["thresholds"]),
                         ("fakehost", "2026-11-14", {"min_runs": 3}))
        self.assertEqual(entry["archive"]["file"], "r1.tar")
        self.assertEqual(len(entry["archive"]["sha256"]), 64)
        self.assertEqual(len(entry["manifest_sha256"]), 64)

    def test_a_round_that_did_not_finish_or_is_not_its_own_is_refused(self):
        for why, (folder, archive) in {"a failed gate": self.round("r2", passed=False),
                                       "another kit": self.round("r3", approved="b" * 64)}.items():
            with self.subTest(why), self.assertRaises(results.ResultsError):
                results.entries(folder, archive)
        folder, _ = self.round("r4")
        _, other = self.round("r5")
        with self.assertRaisesRegex(results.ResultsError, "is not a file or folder of round r4"):
            results.entries(folder, other)

    def test_the_archive_must_hold_the_round_s_store_folder_exactly(self):
        for name in ("manifest.json", "attempts/t1.json", "labels/t1.json", "runs/k1/checks.json"):
            with self.subTest(name):
                folder, archive = self.round(f"r-{name[:3]}")
                changed = folder / name
                changed.parent.mkdir(parents=True, exist_ok=True)
                original = changed.read_bytes() if changed.exists() else b"{}"
                changed.write_bytes(original.replace(b"}", b", \"x\": 1}", 1))
                with tarfile.open(archive, "w") as tar:  # an archive made from the changed folder
                    tar.add(folder, arcname=folder.name)
                changed.write_bytes(original)
                with self.assertRaisesRegex(results.ResultsError, f"1 file\\(s\\) missing or changed, such as {name}"):
                    results.entries(folder, archive)
        folder, archive = self.round("r6")
        (folder / "attempts" / "t2.json").write_bytes((folder / "attempts" / "t1.json").read_bytes())
        (folder / "labels" / "t2.json").write_bytes((folder / "labels" / "t1.json").read_bytes())
        with self.assertRaisesRegex(results.ResultsError, "such as attempts/t2.json, labels/t2.json"):
            results.entries(folder, archive)  # an archive made before a later attempt
        folder, archive = self.round("r7")
        (folder / "runs" / "k1").mkdir(parents=True)
        (folder / "runs" / "k1" / "checks.json").write_text("{}")
        with self.assertRaisesRegex(results.ResultsError, "such as runs/k1/checks.json"):
            results.entries(folder, archive)  # the archive lacks a run's evidence

    def test_rounds_are_listed_apart_and_a_round_again_replaces_its_entry(self):
        old = {"skill_name": "haiku-writer", "hosts": [{"host": "fakehost", "label": "unsupported"},
                                                        {"host": "otherhost", "label": "verified"}]}
        first = results.entries(*self.round("r1"))["haiku-writer"]
        second = results.entries(*self.round("r2"))["haiku-writer"]
        data = results.merge(results.merge(old, "haiku-writer", first), "haiku-writer", second)
        self.assertEqual([r["round"] for r in data["rounds"]], ["r1", "r2"])
        tenth = results.merge(data, "haiku-writer", {**first, "round": "r-10"})
        eighth = results.merge(tenth, "haiku-writer", {**first, "round": "r-8"})
        self.assertEqual([r["round"] for r in eighth["rounds"]], ["r-8", "r-10", "r1", "r2"])
        self.assertEqual(data["phase_2_runner"], [{"host": "otherhost", "label": "verified"}])  # not measured yet
        planned = results.entries(*self.round("r3", skills={"haiku-writer": {"fakehost": HOST, "otherhost": {
            "label": "incomplete", "gaps": ["not run: its probe failed"]}}}))["haiku-writer"]
        kept = results.merge(data, "haiku-writer", planned)  # planned on otherhost, which did not run: kept
        self.assertEqual(kept["phase_2_runner"], [{"host": "otherhost", "label": "verified"}])
        again = results.merge(data, "haiku-writer", {**first, "attempt": "t9"})
        self.assertEqual([(r["round"], r["attempt"]) for r in again["rounds"]], [("r1", "t9"), ("r2", "t1")])
        with self.assertRaises(results.ResultsError):
            results.merge(data, "limerick-writer", first)

    def test_the_label_file_decides_shipped_from_both_labels_and_results_only_copy_it(self):
        met, missed = {"met": True, "gaps": []}, {"met": False, "gaps": ["trigger accuracy 50% below 90%"]}
        for label, trigger, shipped in (("verified", met, True), ("verified", missed, False),
                                        ("unsupported", met, False), ("verified", None, False)):
            with self.subTest(label=label, trigger=trigger):
                hosts = {"fakehost": {**HOST, "label": label, **({"trigger": trigger} if trigger else {})}}
                self.assertIs(labels.shipped(hosts, "fakehost"), shipped)
                self.assertIs(labels.shipped(hosts, "otherhost"), False)  # only the reference host's labels count
        self.assertFalse(hasattr(results, "shipped"))  # results never decide it
        folder, archive = self.round("r8", shipped={"haiku-writer": True})
        self.assertIs(results.entries(folder, archive)["haiku-writer"]["shipped"], True)  # a copy, never a judgement
        folder, archive = self.round("r9")  # a label file written before it decided shipped
        self.assertIsNone(results.entries(folder, archive)["haiku-writer"]["shipped"])

    def test_the_file_reads_back_as_written_one_line_per_field(self):
        folder, archive = self.round(skills={"haiku-writer": {"fakehost": HOST, "otherhost": HOST}})
        out = self.tmp / "results"
        out.mkdir()
        [path] = results.publish(folder, archive, out)
        data = json.loads(path.read_text())
        self.assertEqual(data["rounds"][0]["hosts"], {"fakehost": HOST, "otherhost": HOST})
        self.assertEqual(len(path.read_text().splitlines()), 36)  # 14 fields, each host 4 lines and its braces, compared
        self.assertEqual(results.publish(folder, archive, out), [path])  # the same round again: one entry
        self.assertEqual(len(json.loads(path.read_text())["rounds"]), 1)
