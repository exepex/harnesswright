"""The scrub: every value a bundle keeps is checked for canaries first, then redacted, keys included."""

import json
import types
import unittest
from pathlib import Path

from helpers import TempCase

import scrub

SECRET = 'sk-test-"quoted"\\slash-0123456789'


class Values(unittest.TestCase):
    def test_a_canary_anywhere_stops_the_value_before_it_is_redacted_or_cut(self):
        clean = scrub.Scrub(["HWCANARY-00000000000000aa"], [SECRET])
        for value in ("x" * 9000 + "HWCANARY-00000000000000aa", b"\0bin HWCANARY-00000000000000aa"):
            with self.subTest(value=value[:5]), self.assertRaisesRegex(scrub.Leak, "canary"):
                clean.blob(value) if isinstance(value, bytes) else clean.text(value)
        with self.assertRaisesRegex(scrub.Leak, "canary"):
            clean.value({"files": {"HWCANARY-00000000000000aa.txt": "file 0"}})

    def test_every_form_of_every_secret_is_redacted_however_short(self):
        clean = scrub.Scrub([], [SECRET, "pw7chrs", "", None])
        written = json.dumps({"key": SECRET})  # as a host's JSON event line holds it
        self.assertNotIn("sk-test", clean.text(f"{SECRET} and {written}"))
        self.assertEqual(clean.text("the pw7chrs password"), "the [redacted] password")
        self.assertEqual(clean.blob(SECRET.encode() + b"\xff"), b"[redacted]\xff")

    def test_keys_are_scrubbed_and_two_keys_that_become_one_are_refused(self):
        clean = scrub.Scrub([], [SECRET])
        self.assertEqual(clean.value({f"k-{SECRET}": [1, None, True, f"v {SECRET}"]}),
                         {"k-[redacted]": [1, None, True, "v [redacted]"]})
        with self.assertRaisesRegex(scrub.Collision, "both 'a-\\[redacted\\]'"):
            clean.value({f"a-{SECRET}": "x", "a-[redacted]": "y"})
        with self.assertRaises(TypeError):
            clean.value({"a": b"bytes"})

    def test_neutral_words_apply_only_to_a_transcript(self):
        clean = scrub.Scrub([], [], {"haiku-writer": scrub.NEUTRAL_NAME, "skills/haiku-writer": scrub.NEUTRAL_PATH})
        line = "loaded skills/haiku-writer/SKILL.md for haiku-writer"
        self.assertEqual(clean.text(line, neutral=True), "loaded guide-folder/SKILL.md for project-guide")
        self.assertEqual(clean.text(line), line)


class Credentials(TempCase):
    def test_a_run_s_credentials_are_its_keys_url_users_and_credential_files(self):
        operator, home = self.tmp / "operator", self.tmp / "home"
        for folder, token in ((operator, "refresh-AAAAAAAAAA"), (home, "refresh-BBBBBBBBBB")):  # refreshed by host
            (folder / ".h").mkdir(parents=True)
            (folder / ".h" / "auth.json").write_text(json.dumps({"type": "Bearer", "tokens": [{"refresh": token}]}))
        contained = types.SimpleNamespace(
            adapter=types.SimpleNamespace(ENV_KEYS=("H_KEY", "H_URL", "H_NONE"), CREDENTIAL_FILES=(".h/auth.json",)),
            operator_env={"H_KEY": "key-0123456789", "H_URL": "https://user1234:pass567@model.example"},
            upstream="http://proxyuser:proxypass@10.0.0.1:3128", operator_home=Path(operator), home=Path(home))
        found = scrub.credentials(contained)
        for value in ("key-0123456789", "user1234", "pass567", "proxyuser", "proxypass", "refresh-AAAAAAAAAA",
                      "refresh-BBBBBBBBBB"):
            self.assertIn(value, found)
        self.assertNotIn("https://user1234:pass567@model.example", found)  # the URL's host is not a secret
        self.assertNotIn("Bearer", found)  # a short string in a credential file is its metadata


if __name__ == "__main__":
    unittest.main()
