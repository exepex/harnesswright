"""Evidence: a run is read once into manifests and leaves only through one scrub, into a bundle of hashed blobs."""

import contextlib
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import TempCase
from test_host import FAKE, JAIL, changed, fake_adapter

import contain
import evidence
import host
import manifest
import scrub
import world

SECRET = "fake-key-0123456789abcdef"
TOKEN = "refresh-0123456789abcdef"


class Diff(unittest.TestCase):
    def test_a_diff_lists_every_change_but_the_paths_it_leaves_out(self):
        before = {"a": "dir", "a/x": "file 1", "b": "file 2", "s": "dir", "s/SKILL.md": "file 3"}
        after = {"a": "dir", "a/x": "file 1 x", "c": "link b", "s": "dir", "s/SKILL.md": "file 4", "sx": "dir",
                 "d": "dir", "d/e": "dir", "d/e/f": "file 5", "d/g": "file 6"}
        self.assertEqual(evidence.diff(before, after, ["s", "d/e"]), {"d/g": {"before": None, "after": "file 6"},
            "a/x": {"before": "file 1", "after": "file 1 x"}, "b": {"before": "file 2", "after": None},
            "c": {"before": None, "after": "link b"}, "sx": {"before": None, "after": "dir"}})
        self.assertEqual(evidence.diff({}, {"h": "dir", "h/x": "file 8"}, exact=["h"]),
                         {"h/x": {"before": None, "after": "file 8"}})  # a host's own folder hides only itself
        # A folder above a left-out path is left out only while it is a folder that holds it.
        self.assertEqual(evidence.diff({"s": "dir", "s/k": "dir"}, {"s": "file 7"}, ["s/k"]),
                         {"s": {"before": "dir", "after": "file 7"}})


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Bundles(TempCase):
    """The fake host runs in a real jail, and its run becomes a bundle."""

    def run_of(self, actions, adapter=None, tokens=(), arm=True, key=SECRET, case=None):
        adapter = adapter or fake_adapter()
        tool = self.tmp / "tool"
        if not tool.exists():
            shutil.copytree(FAKE, tool, ignore=shutil.ignore_patterns("adapter.py", "__pycache__"))
            self.skill()
            operator = self.tmp / "operator" / ".fake"
            operator.mkdir(parents=True)
            (operator / "creds.json").write_text(json.dumps({"refresh": TOKEN}))
        case = case or self.case({"README.md": "A notes app.\n"})
        run = os.urandom(4).hex()  # a run's folders never name its arm
        built = world.build(case, adapter, self.tmp / f"arm-{run}", self.tmp / "skills", with_skill=arm)
        contained = contain.Containment(adapter, "task", built.path, manifest.manifest(built.path),
                                        root=self.tmp / f"run-{run}", tokens=tokens,
                                        operator_env={"PATH": f"{tool}:/usr/bin:/bin", "FAKE_API_KEY": key},
                                        operator_home=self.tmp / "operator", host_paths=[tool])
        result = host.run(contained, json.dumps(actions), skills=["haiku-writer"] if arm else [], timeout=120)
        layer = evidence.overlay(case, adapter, self.tmp / "skills")
        drift = {"own files": {"task": ["world/.fake-state", "home/.fake/log"]}}
        return evidence.collect(contained, result, case, "with_skill" if arm else "without_skill", layer, drift,
                                "fakehost 1.0", "fast-model")

    def stored(self, record, blobs):
        out = evidence.store(record, blobs, self.tmp / "bundles" / "b1")
        return out, *evidence.load(out)

    def test_a_run_becomes_one_bundle_of_a_record_and_hashed_blobs(self):
        actions = [{"do": "write", "path": "notes.txt", "text": "hi\n"},
                   {"do": "command", "command": "ln -s README.md link.md && printf x > .fake-state"},
                   {"do": "write", "path": "skills/haiku-writer/notes.md", "text": "edited"},
                   {"do": "command", "command": "mkfifo pipe && pwd"},
                   {"do": "skill", "name": "haiku-writer"}, {"do": "say", "text": "Done with haiku-writer."}]
        out, record, blob = self.stored(*self.run_of(actions))
        self.assertEqual(sorted(record["diff"]), ["link.md", "notes.txt", "pipe"])  # not the skill, not a self-write
        self.assertEqual(record["files_after"]["pipe"], "other")  # a pipe the agent made is evidence, not a fault
        self.assertEqual(record["diff"]["link.md"], {"before": None, "after": "link README.md"})
        self.assertEqual(blob(record["diff"]["notes.txt"]["after"].split(" ")[1]), b"hi\n")
        self.assertIn("skills/haiku-writer/notes.md", record["files_after"])
        self.assertEqual(record["overlay"], {"skill": "haiku-writer", "row": None, "index": None, "index_without": None,
                                             "paths": ["skills/haiku-writer", ".fake/skills/haiku-writer"]})
        self.assertEqual((record["arm"], record["final_message"], record["model"]),
                         ("with_skill", "Done with haiku-writer.", "fast-model"))
        self.assertEqual(" ".join(e["kind"] for e in record["log"]), "write command write command skill message")
        stdout = blob(record["transcript"]["stdout"]).decode()
        self.assertNotIn("haiku-writer", stdout)  # the transcript names neither the skill nor its paths
        self.assertIn(scrub.NEUTRAL_NAME, stdout)
        self.assertNotIn(str(self.tmp), stdout)  # nor the run's folders, whose names may tell the arm
        self.assertIn(scrub.NEUTRAL_FOLDERS["world"], stdout)
        self.assertGreaterEqual(record["seconds"], 0)
        names = [os.path.relpath(os.path.join(r, n), out) for r, ds, fs in os.walk(out) for n in ds + fs]
        self.assertTrue(all(n in ("bundle.json", "blobs") or n.startswith("blobs/") for n in names), names)
        self.assertFalse(any(os.path.islink(out / n) for n in names))

    def test_no_secret_leaves_through_a_name_a_link_a_file_a_command_or_a_message(self):
        adapter = changed(fake_adapter(), ENV_KEYS=("FAKE_API_KEY",), CREDENTIAL_FILES=(".fake/creds.json",))
        actions = [{"do": "command", "command": 'printf %s "$FAKE_API_KEY" > "k-$FAKE_API_KEY" && echo "$FAKE_API_KEY"'
                                                ' && ln -s "$FAKE_API_KEY" lnk && cat "$HOME/.fake/creds.json" > c'},
                   {"do": "command", "command": 'printf "%3990s" "" && echo "$FAKE_API_KEY"'},  # across the cut
                   {"do": "write", "path": "t.json", "text": json.dumps({"t": TOKEN})},
                   {"do": "say", "text": f"The key is {SECRET}."}]
        out, record, _ = self.stored(*self.run_of(actions, adapter))
        for path in [out / "bundle.json", *(out / "blobs").iterdir()]:
            data = path.read_bytes()
            self.assertNotIn(SECRET.encode(), data, path)
            self.assertNotIn(TOKEN.encode(), data, path)
        self.assertIn("k-[redacted]", record["files_after"])
        self.assertEqual(record["files_after"]["lnk"], "link [redacted]")
        self.assertEqual(record["final_message"], "The key is [redacted].")
        self.assertEqual(len(record["log"][1]["output"]), 3990 + len("[redacted]\n"))  # kept whole and redacted
        token = contain.new_token()
        with self.assertRaises(scrub.Leak) as caught:  # a reason never repeats a secret the run put in a name
            self.run_of([{"do": "command", "command": f'printf {token} > "k-$FAKE_API_KEY"'}], adapter, [token])
        self.assertNotIn(SECRET, str(caught.exception))

    def test_a_canary_in_any_output_voids_the_run_even_past_the_cut(self):
        token = contain.new_token()
        long = f"python3 -c \"print('x' * 5000 + '{token}')\""
        for actions, where in (([{"do": "write", "path": "n.txt", "text": token}], "world/n.txt"),
                               ([{"do": "command", "command": long}], "stdout"),
                               ([{"do": "command", "command": f"printf {token} > $HOME/kept"}], "home/kept"),
                               ([{"do": "command", "command": f"ln -s {token} $HOME/to"}], "home/to"),
                               ([{"do": "command", "command": f"touch $HOME/{token}"}], "home/")):
            with self.subTest(where=where), self.assertRaisesRegex(scrub.Leak, where):
                self.run_of(actions, tokens=[token])

    def test_a_value_the_harness_chose_is_kept_whatever_the_credential(self):
        adapter = changed(fake_adapter(), ENV_KEYS=("FAKE_API_KEY",))
        for key in ("98ea6e4f", "observed"):  # the start of the hash of "hi\n", and a source tag
            record, _ = self.run_of([{"do": "write", "path": "n.txt", "text": "hi\n"}], adapter, key=key)
            with self.subTest(key=key):
                self.assertEqual((record["log"][0]["source"], record["log"][0]["sha256"]),
                                 ("observed", host.sha256("hi\n")))
                host.check_log(record["log"])

    def test_what_the_scan_cannot_read_refuses_the_run_and_names_no_secret(self):
        clean = scrub.Scrub([], [SECRET])
        (self.tmp / "home").mkdir()
        (self.tmp / "home" / f"k-{SECRET}").write_text("")
        (self.tmp / "not-a-folder").write_text("")  # os.walk reports it as it reports a folder it may not read
        denied = PermissionError(13, "Permission denied", str(self.tmp / "home" / f"k-{SECRET}"))
        for folder, patch in ((self.tmp / "not-a-folder", None), (self.tmp / "home", denied)):
            with self.subTest(folder=folder.name), mock.patch.object(Path, "read_bytes", side_effect=patch) \
                    if patch else contextlib.nullcontext():
                with self.assertRaisesRegex(evidence.EvidenceError, "cannot scan home/") as caught:
                    evidence._scan(folder, "home", clean)
                self.assertNotIn(SECRET, str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)

    def test_the_without_skill_arm_has_the_same_shape_and_leaves_out_the_same_paths(self):
        made = "mkdir -p skills/haiku-writer && echo > skills/haiku-writer/x.md"
        record, _ = self.run_of([{"do": "command", "command": made}, {"do": "say", "text": "ok"}], arm=False)
        self.assertEqual((record["arm"], record["diff"]), ("without_skill", {}))
        self.assertIn("skills/haiku-writer/x.md", record["files_after"])

    def test_a_bundle_is_stored_once_outside_the_repository_and_read_back_by_hash(self):
        short = changed(fake_adapter(), ENV_KEYS=("FAKE_API_KEY",))
        with self.assertRaisesRegex(contain.ContainmentError, "cannot be redacted reliably"):
            self.run_of([], short, key="a")  # it would damage the evidence, so the run never starts
        record, blobs = self.run_of([{"do": "say", "text": "ok"}])
        with self.assertRaisesRegex(evidence.EvidenceError, "outside the repository"):
            evidence.store(record, blobs, world.REPO / "evals" / "results" / "b")
        with self.assertRaisesRegex(evidence.EvidenceError, "do not name the same files"):
            evidence.store(record, {**blobs, "0" * 64: b""}, self.tmp / "b0")
        out, _, _ = self.stored(record, blobs)
        with self.assertRaisesRegex(evidence.EvidenceError, "already exists"):
            evidence.store(record, blobs, out)
        stdout = out / "blobs" / record["transcript"]["stdout"]
        kept = stdout.read_bytes()
        stdout.unlink()
        with self.assertRaisesRegex(evidence.EvidenceError, "not exactly the ones the record names"):
            evidence.load(out)
        stdout.write_bytes(kept + b"changed")
        with self.assertRaisesRegex(evidence.EvidenceError, "does not have its hash"):
            evidence.load(out)


if __name__ == "__main__":
    unittest.main()
