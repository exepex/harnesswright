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

    def test_names_the_run_chose_are_scrubbed_and_the_record_s_own_fields_are_kept(self):
        clean = scrub.Scrub([], [SECRET, "out", "p%40ss%2Fw0rd"])
        self.assertEqual(clean.names({f"k-{SECRET}": "file ab"}), {"k-[redacted]": "file ab"})
        self.assertEqual(clean.value({"k": [1, None, True, f"v {SECRET}"]}), {"k": [1, None, True, "v [redacted]"]})
        with self.assertRaisesRegex(scrub.Collision, "both 'a-\\[redacted\\]'"):
            clean.names({f"a-{SECRET}": "x", "a-[redacted]": "y"})
        self.assertEqual(clean.value({"output": "out"}), {"output": "[redacted]"})  # a field's name is kept
        self.assertEqual(clean.text("p@ss/w0rd and p%40ss%2Fw0rd"), "[redacted] and [redacted]")  # decoded too
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
            operator_env={"H_KEY": "key-0123456789", "H_URL": "https://u:pass5678@model.example"},
            upstream="http://proxyuser:proxypass@10.0.0.1:3128", operator_home=Path(operator), home=Path(home))
        found = scrub.credentials(contained)
        for value in ("key-0123456789", "pass5678", "u:pass5678", "proxypass", "proxyuser:proxypass",
                      "refresh-AAAAAAAAAA", "refresh-BBBBBBBBBB"):
            self.assertIn(value, found)
        self.assertNotIn("u", found)  # a user name beside a password is not a credential, nor the URL's host
        self.assertNotIn("Bearer", found)  # a short string in a credential file is its metadata
        contained.operator_env["H_URL"] = "https://u:%70ass5678@m.example"  # needlessly encoded, kept as written
        self.assertEqual(scrub.Scrub([], scrub.credentials(contained)).text(contained.operator_env["H_URL"]),
                         "https://[redacted]@m.example")
        for url in ("https://u:pw7char@m.example", "https://u:%61%62%63@m.example", 'https://u:quo"ted-pass@m.example'):
            contained.operator_env["H_URL"] = url  # too short once decoded, or a character JSON would escape
            with self.subTest(url=url), self.assertRaisesRegex(scrub.UnsafeCredential, "H_URL cannot"):
                scrub.credentials(contained)


if __name__ == "__main__":
    unittest.main()
