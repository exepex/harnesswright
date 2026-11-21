"""The rule of `stated`: a value a case's texts state about its world is one the built world gives."""

import types
import unittest

from helpers import TempCase

import stated
import world


def case(question, prompt="Write the skill."):
    return types.SimpleNamespace(prompt=prompt, expectations=[
        {"text": "The version is raised", "judged": {"question": question, "pass": "Yes.", "fail": "No.",
                                                     "examples": {"pass": ["Yes."], "fail": ["No."]}}}])


class Stated(TempCase):
    def arm(self, files, history=False, name="world"):
        root = self.tmp / name
        for path, text in files.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text)
        if history:
            world._git(root, "init", "-q")
            world._git(root, "add", "-A")
            world._git(root, "commit", "-q", "-m", "Start")
        return types.SimpleNamespace(path=root)

    def test_a_version_is_the_built_worlds_or_one_raise_of_it(self):
        arm = self.arm({"v2/VERSION": "0.8.0\n"})
        for good in ("0.8.0", "0.8.1", "0.9.0", "1.0.0"):
            self.assertEqual(stated.check(case(f"Does v2/VERSION read {good}?"), arm), [])
        for old in ("0.7.0", "0.7.1", "0.8.2", "0.10.0"):
            [problem] = stated.check(case(f"v2/VERSION read {old} before the run?"), arm)
            self.assertIn(f"states version {old!r}", problem)
        [problem] = stated.check(case("Is it ready?", prompt="Raise v2/VERSION from 0.7.0."), arm)  # the prompt too
        self.assertIn("'0.7.0'", problem)

    def test_a_version_is_free_in_a_world_with_no_version_file(self):
        self.assertEqual(stated.check(case("Is the profile at 0.7.0?"), self.arm({"README.md": "A tool.\n"})), [])

    def test_a_commit_is_one_of_the_built_history_or_spelled_by_a_world_file(self):
        arm = self.arm({"README.md": "A tool.\n", "evals/label.json": '{"commit": "1a2b3c4d5e6f"}\n'}, history=True)
        head = world._git(arm.path, "rev-parse", "HEAD").strip()
        self.assertEqual(stated.check(case(f"Is the label at {head[:12]}?"), arm), [])
        self.assertEqual(stated.check(case("Is the label at 1a2b3c4?"), arm), [])  # a file spells it
        [problem] = stated.check(case("Is the label at 9443ad2ddb32?"), arm)
        self.assertIn("'9443ad2ddb32'", problem)
        self.assertEqual(stated.check(case("Are 1234567 rows and the word facade kept?"), arm), [])  # no hash

    def test_in_a_world_with_history_a_label_and_a_question_naming_an_old_commit_fail_together(self):
        old = "9443ad2ddb32aa43cff14192c7fdf6e67ad9dd67"
        files = {"README.md": "A tool.\n", "evals/results/notice.json": f'{{"commit": "{old}"}}\n',
                 "incoming/ORIGIN.md": "Source: example-org/kit at 1a2b3c4.\n"}
        arm = self.arm(files, history=True)
        [problem] = stated.check(case(f"Is the label at {old[:12]}, the commit its round ran on?"), arm)
        self.assertIn(f"{old[:12]!r}", problem)
        self.assertEqual(stated.check(case("Does the metadata name example-org/kit at 1a2b3c4?"), arm), [])
        bare = self.arm(files, name="bare")  # with no history the label is all the world has
        self.assertEqual(stated.check(case(f"Is the label at {old[:12]}?"), bare), [])

    def test_a_world_line_is_never_named_by_its_number(self):
        arm = self.arm({"docs/design/11-evals.md": "# Evals\n" * 300})
        [problem] = stated.check(case("Is it judged in the shape docs/design/11-evals.md:269 gives?"), arm)
        self.assertIn("names line 269 of the world file docs/design/11-evals.md", problem)
        self.assertEqual(stated.check(case("Is it judged in the shape doc 11 gives under Graders?"), arm), [])
        self.assertEqual(stated.check(case("Did it start at 10:30 and leave src/app.py:12 alone?"), arm), [])


if __name__ == "__main__":
    unittest.main()
