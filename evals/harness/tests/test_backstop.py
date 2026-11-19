"""The baseline backstop: a without-skill run is void only for one long unbroken passage of the skill's own text in
one of its texts; shorter matches, and matches that only add up across texts, are listed, never a void."""

import json
import unittest

import backstop
from textruns import RUN, runs

SKILL = ("count the syllables of every line twice before you write it down and keep the season word in the first "
         "line so the reader knows the time of year")
OWN = runs(SKILL, {RUN})


def record(final="", files=None, stdout="", log=None):
    blobs, diff = {"t": stdout.encode()}, {}
    for number, (path, text) in enumerate((files or {}).items()):
        digest = f"{number:064x}"
        blobs[digest] = text.encode()
        diff[path] = {"before": None, "after": f"file {digest} 0644"}
    return {"final_message": final, "diff": diff, "transcript": {"stdout": "t"}, "log": log or []}, blobs.__getitem__


class Matches(unittest.TestCase):
    def test_a_long_copied_passage_in_one_text_is_a_void(self):
        found = backstop.check(*record(files={"notes.md": f"Notes. {SKILL}. The end."}), OWN)
        self.assertEqual([(where, length) for where, length, _ in found["void"]], [("world/notes.md", len(SKILL.split()))])
        self.assertEqual(found["short"], [])

    def test_a_match_shorter_than_the_span_is_listed_not_a_void(self):
        eight = " ".join(SKILL.split()[:8])
        found = backstop.check(*record(final=f"I will {eight} now."), OWN)
        self.assertEqual((found["void"], [m[1] for m in found["short"]]), ([], [8]))

    def test_matches_in_different_texts_or_found_again_never_add_up(self):
        first, second = " ".join(SKILL.split()[:10]), " ".join(SKILL.split()[12:22])
        stdout = "\n".join(json.dumps({"text": part}) for part in (first, first, second))
        found = backstop.check(*record(final=first, stdout=stdout), OWN)
        self.assertEqual(found["void"], [])
        self.assertEqual([m[1] for m in found["short"]], [10, 10])  # each distinct span once

    def test_transcript_lines_are_read_one_string_at_a_time(self):
        half = len(SKILL.split()) // 2
        a, b = " ".join(SKILL.split()[:half]), " ".join(SKILL.split()[half:])
        stdout = json.dumps({"a": a, "b": b})  # one line, two strings: words never run together across them
        self.assertEqual(backstop.check(*record(stdout=stdout), OWN)["void"], [])
        plain = f"{a} {b}"  # a line that is not JSON is read whole
        self.assertEqual(len(backstop.check(*record(stdout=plain), OWN)["void"]), 1)

    def test_a_passage_only_in_the_action_log_is_a_void(self):
        log = [{"kind": "command", "source": "observed", "command": "cat notes.md", "output": SKILL}]
        found = backstop.check(*record(log=log), OWN)  # a sub-agent's output that only the host's log reports
        self.assertEqual([where for where, _, _ in found["void"]], ["log 0"])

    def test_text_that_shares_no_run_with_the_skill_matches_nothing(self):
        found = backstop.check(*record(final="A haiku about the sea, in three short lines."), OWN)
        self.assertEqual(found, {"void": [], "short": []})


if __name__ == "__main__":
    unittest.main()
