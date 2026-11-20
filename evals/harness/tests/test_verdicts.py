"""The task verdict and trigger outcomes: a run's outcome, a skill's measures and its label by the thresholds of
10 · Skills, each gap and doubt named."""

import unittest

from test_labels import EXPECTATIONS, case, verdict

import triggers
import verdicts


class Outcomes(unittest.TestCase):
    def test_a_task_run_counts_its_contract_expectations_a_check_first_then_a_trusted_answer(self):
        self.assertEqual(verdicts.task_outcome(case(), [verdict("fail"), None, verdict("pass")], {"q2": "yes"}),
                         (True, ""))  # the format check that failed does not count
        self.assertEqual(verdicts.task_outcome(case(), [verdict("pass"), None, verdict("pass")], {"q2": "no"}),
                         (False, "expectation 2 failed"))
        self.assertEqual(verdicts.task_outcome(case(), [verdict("pass"), None, verdict("undecidable")],
                                               {"q2": "yes", "q3": "no"}), (False, "expectation 3 failed"))
        self.assertEqual(verdicts.task_outcome(case(), [verdict("pass"), None, verdict("pass")], {}),
                         (None, "expectation 2 has no trusted answer"))  # untrusted or unanswered
        self.assertEqual(verdicts.task_outcome(case(), [verdict("pass"), None, verdict("fail")], {})[0], False)
        self.assertEqual(verdicts.task_outcome(case(expectations=EXPECTATIONS[:1]), [verdict("pass")], {}),
                         (None, "the case has no contract expectation"))

    def test_a_trigger_run_passes_when_the_skill_loaded_exactly_when_it_should_an_inferred_load_named(self):
        def load(name, source="observed"):
            return [{"kind": "skill", "source": source, "name": name}]

        should, should_not = case("trigger", should_trigger=True), case("trigger", should_trigger=False)
        self.assertEqual(triggers.trigger_outcome(should, load("haiku-writer")), (True, False))
        self.assertEqual(triggers.trigger_outcome(should, load("other-skill")), (False, False))
        self.assertEqual(triggers.trigger_outcome(should_not, load("other-skill")), (True, False))
        self.assertEqual(triggers.trigger_outcome(should_not, load("haiku-writer")), (False, False))
        self.assertEqual(triggers.trigger_outcome(should, load("haiku-writer", "inferred")), (True, True))
        self.assertEqual(triggers.trigger_outcome(should_not, load("haiku-writer", "inferred")), (False, True))
        both = load("haiku-writer", "inferred") + load("haiku-writer")
        self.assertEqual(triggers.trigger_outcome(should, both), (True, False))


OWN = ["file_state"]  # the check the contract expectation of EXPECTATIONS runs, listed as harnesswright's own
NOTHING = {"listed": [], "cases": {}}  # a skill whose situation list leaves every situation out


def summary(cases, scored, situations=NOTHING, kind="team", **flags):
    return verdicts.summary(cases, scored, situations=situations, kind=kind, **flags)


def formatted(passed=9, decided=10, undecided=0):
    """The format conformance of the with-skill arm, as the label's measures hold it: one run of case t."""
    return {"format_conformance": {"with_skill": {"rate": None, "passed": passed, "decided": decided,
                                                  "undecided": undecided}},
            "format_runs": {"with_skill": {"t": [[passed, decided + undecided]]} if decided + undecided else {}}}


def decided(*args, **options):
    """The label and gaps `verdicts.decide` gives, without each measure's verdict."""
    found = verdicts.decide(*args, **options)
    return {"label": found["label"], "gaps": found["gaps"]}


def measured(task=(1, 1, 1), baseline=(0, 0, 0), trigger=(1, 1, 1), train=None, should=True, form=(9, 10, 0)):
    cases = {"t": case(), "g": case("trigger", should_trigger=should, split="test")}
    scored = {("t", "with_skill"): [bool(o) for o in task], ("t", "without_skill"): [bool(o) for o in baseline],
              ("g", "with_skill"): [bool(o) for o in trigger]}
    if train is not None:
        cases["x"] = case("trigger", should_trigger=True, split="train")
        scored[("x", "with_skill")] = train
    return {**summary(cases, scored), **(formatted(*form) if form else {})}


def against(task=(1, 1, 1), before=(1, 1, 0), done=(0, 3), done_before=(0, 3)):
    """The measures of a skill whose round ran a previous version, and the false-done tally of each arm."""
    cases = {"t": case(), "g": case("trigger", should_trigger=True, split="test")}
    scored = {("t", "with_skill"): [bool(o) for o in task], ("t", "without_skill"): [False] * 3,
              ("t", "previous_version"): [bool(o) for o in before], ("g", "with_skill"): [True] * 3}
    tally = {("t", arm): {"false_done": f, "decided": d, "undecided": 0}
             for arm, (f, d) in (("with_skill", done), ("previous_version", done_before))}
    return {**summary(cases, scored, previous=True), **formatted()}, tally


class Previous(unittest.TestCase):
    def test_a_skill_at_least_as_good_as_its_previous_version_is_verified(self):
        found, tally = against()
        self.assertEqual((found["previous_pass_rate"], found["runs"]["t, previous_version"]), (0.6667, 3))
        self.assertEqual(decided(found, [], false_done=tally), {"label": "verified", "gaps": []})
        found, tally = against(before=(1, 1, 1))  # equal is at least as good
        self.assertEqual(decided(found, [], false_done=tally), {"label": "verified", "gaps": []})

    def test_a_skill_worse_than_its_previous_version_is_unsupported_with_each_gap_named(self):
        found, tally = against(task=(0,) * 3, before=(1,) * 3, done=(3, 3), done_before=(0, 3))
        self.assertEqual(decided(found, [], false_done=tally)["gaps"][-2:], [
            "task pass rate 0% below the previous version's 100%",
            "false-done rate 3 of 3 above the previous version's 0 of 3"])
        found, tally = against(task=(1,) * 9 + (0,), before=(1,) * 10, done=(1, 10), done_before=(0, 10))
        self.assertEqual(decided(found, [], false_done=tally), {"label": "too close", "gaps": [
            "task pass rate too close: 90% as measured, 80% at worst, 100% at best",
            "previous pass rate too close: -10% as measured, -20% at worst, 0% at best",
            "previous false-done rate too close: -10% as measured, -20% at worst, 0% at best"]})  # one split case

    def test_too_few_previous_runs_or_no_decided_false_done_keep_the_label_inconclusive(self):
        found, tally = against(before=(1, 1))
        self.assertEqual(decided(found, [], false_done=tally),
                         {"label": "inconclusive", "gaps": ["t, previous_version: 2 scored run(s), 3 needed"]})
        found, tally = against(done_before=(0, 0))
        self.assertEqual(decided(found, [], false_done=tally)["gaps"],
                         ["false-done rate: no decided run in the with-skill or the previous version's arm"])

    def test_a_previous_version_doubt_unsettles_the_reference_host_too(self):
        found, tally = against(done_before=(0, 0))  # the one list `labels` settles the reference host on
        self.assertEqual(verdicts.doubts(found, [], tally),
                         ["false-done rate: no decided run in the with-skill or the previous version's arm"])

    def test_a_round_with_no_previous_version_is_decided_as_before(self):
        self.assertNotIn("previous_pass_rate", measured())
        self.assertNotIn("t, previous_version", measured()["runs"])


class Decide(unittest.TestCase):
    def test_enough_runs_meeting_every_threshold_with_lift_are_verified(self):
        found = measured(train=[False] * 3)  # the train split is for tuning: it does not count
        self.assertEqual((found["task_pass_rate"], found["baseline_pass_rate"], found["lift"]), (1.0, 0.0, 1.0))
        self.assertNotIn("trigger_accuracy", found)  # the trigger label's, a line of its own
        self.assertEqual(decided(found, []), {"label": "verified", "gaps": []})
        self.assertEqual(decided(found, [], measured(), None), {"label": "verified", "gaps": []})

    def test_a_skill_with_no_task_case_is_incomplete_and_one_with_no_trigger_case_is_not(self):
        no_triggers = {**summary({"t": case()}, {("t", "with_skill"): [True] * 3,
                                                        ("t", "without_skill"): [False] * 3}), **formatted()}
        self.assertEqual(decided(no_triggers, ["t, with_skill, run 4: not scored (void)"]),
                         {"label": "inconclusive", "gaps": ["t, with_skill, run 4: not scored (void)"]})
        no_tasks = {**summary({"g": case("trigger", should_trigger=True, split="test")},
                              {("g", "with_skill"): [True] * 3}), **formatted()}
        label = decided(no_tasks, [])
        self.assertEqual((label["label"], label["gaps"][0]), ("incomplete", "task cases: none"))

    def test_a_skill_with_no_folder_yet_gives_its_baseline_and_is_incomplete(self):
        found = summary({"t": case()}, {("t", "without_skill"): [True, False, False]}, absent=True)
        self.assertEqual((found["absent"], found["baseline_pass_rate"], found["task_pass_rate"], found["runs"]),
                         (True, 0.3333, None, {"t, without_skill": 3}))
        label = decided({**found, **formatted()}, [])
        self.assertEqual(label["label"], "incomplete")
        self.assertEqual(label["gaps"][0], "the skill: no folder yet, a baseline round")

    def test_every_doubt_is_named_and_keeps_the_label_inconclusive(self):
        found = decided(measured(task=(1, 1)), [])
        self.assertEqual(found, {"label": "inconclusive", "gaps": ["t, with_skill: 2 scored run(s), 3 needed"]})
        self.assertEqual(decided(measured(trigger=()), []), {"label": "verified", "gaps": []})  # its own line
        unscored = ["t, with_skill, run 4: not scored (expectation 2 has no trusted answer)",
                    "t, with_skill, run 5: not scored (empty)", "haiku-writer/t q2: goldens missed (planted)"]
        self.assertEqual(decided(measured(), unscored), {"label": "inconclusive", "gaps": unscored})
        self.assertIn("no lift", decided(measured(baseline=(1, 1, 1)), [])["gaps"][0])

    def test_another_host_is_never_verified_on_a_reference_result_that_is_not_settled(self):
        found = decided(measured(), [], None, "the reference host claude-code's result is not settled")
        self.assertEqual(found, {"label": "inconclusive",
                                 "gaps": ["the reference host claude-code's result is not settled"]})

    def test_format_conformance_below_its_floor_is_unsupported_and_an_undecided_answer_does_not_pass(self):
        self.assertEqual(decided(measured(form=(17, 20, 0)), []), {"label": "unsupported", "gaps": [
            "format conformance 85% below 90% (17 of 20, 0 undecided)"]})
        self.assertEqual(decided(measured(form=(18, 19, 1)), []), {"label": "verified", "gaps": []})  # 90%
        self.assertEqual(decided(measured(form=(17, 19, 1)), [])["gaps"],
                         ["format conformance 85% below 90% (17 of 20, 1 undecided)"])

    def test_the_format_floor_never_replaces_the_lift(self):
        found = decided(measured(baseline=(1, 1, 1), form=(10, 10, 0)), [])
        self.assertEqual(found["label"], "inconclusive")
        self.assertIn("no lift", found["gaps"][0])

    def test_a_format_floor_not_measured_keeps_the_label_inconclusive(self):
        for form in (None, (0, 0, 0)):
            with self.subTest(form=form):
                self.assertEqual(decided(measured(form=form), []), {"label": "inconclusive", "gaps": [
                    "format conformance: no format expectation was asked in the with-skill arm"]})

    def test_a_missed_threshold_is_unsupported_with_each_gap_named(self):
        found = decided(measured(task=(0, 0, 0), trigger=(0, 0, 1)), [], measured(), None)
        self.assertEqual(found["label"], "unsupported")  # the trigger miss is the trigger label's, not named here
        self.assertEqual(found["gaps"], ["task pass rate 0% below 90%", "task pass rate 100% below the reference host"])



class Verdicts(unittest.TestCase):
    def test_a_clean_round_is_decided_at_once(self):
        found = verdicts.decide(measured(), [])["verdicts"]
        self.assertEqual(found["task pass rate"], {"verdict": "pass", "value": 1.0, "best": 1.0, "worst": 1.0,
                                                  "split": {"with_skill": []}})  # nothing to extend
        self.assertEqual(found["lift"], {"verdict": "pass", "value": 1.0, "best": 1.0, "worst": 1.0,
                                         "split": {"with_skill": [], "without_skill": []}})

    def test_a_split_case_makes_a_measure_too_close_and_one_failing_at_its_best_fails(self):
        two = {"t": case(), "u": case()}  # the rate is the mean of per-case rates: (9/10 + 1) / 2
        scored = {("t", "with_skill"): [True] * 9 + [False], ("u", "with_skill"): [True] * 3,
                  ("t", "without_skill"): [False] * 10, ("u", "without_skill"): [False] * 3}
        found = {**summary(two, scored), **formatted()}
        self.assertEqual(found["task_pass_rate"], 0.95)  # pooled counts would give 12 of 13, 92%
        self.assertEqual(verdicts.decide(found, [])["verdicts"]["task pass rate"],
                         {"verdict": "pass", "value": 0.95, "best": 1.0, "worst": 0.9, "split": {"with_skill": ["t"]}})
        self.assertEqual(decided(measured(task=(1, 1, 1, 1, 0)), []), {"label": "too close", "gaps": [
            "task pass rate too close: 80% as measured, 60% at worst, 100% at best"]})
        self.assertEqual(decided(measured(task=(1, 0, 0)), []), {"label": "unsupported", "gaps": [
            "task pass rate 33% below 90%"]})  # 67% even at its best

    def test_a_two_arm_measure_moves_each_arm_its_own_way(self):
        lift = verdicts.judged(measured(task=(1, 1, 0), baseline=(1, 0, 0)))["lift"]
        self.assertEqual(lift, {"verdict": "too close", "value": 0.3333, "best": 1.0, "worst": -0.3333,
                                "split": {"with_skill": ["t"], "without_skill": ["t"]}})
        self.assertEqual(decided(measured(task=(1, 1, 1), baseline=(1, 1, 0)), [])["label"], "too close")
        self.assertEqual(decided(measured(task=(1, 1, 1), baseline=(1, 1, 1)), []), {"label": "inconclusive", "gaps": [
            "no lift over the baseline (100% with the skill, 100% without)"]})  # a failed lift is no failure

    def test_format_conformance_flips_the_items_of_one_run(self):
        found = {**measured(), "format_runs": {"with_skill": {"t": [[3, 4], [4, 4]]}}}
        self.assertEqual(verdicts.judged(found)["format conformance"],
                         {"verdict": "too close", "value": 0.875, "best": 1.0, "worst": 0.375,
                          "split": {"with_skill": ["t"]}})
        self.assertEqual(verdicts.mean({"t": [[3, 4]]}, 1), 0.75)  # one run: no split, never moved

    def test_an_internal_skill_too_close_is_too_close_and_never_verified(self):
        found = {**summary({"t": case()}, {("t", "with_skill"): [True] * 4 + [False]}, kind="internal",
                           own_checks=OWN), **formatted()}
        self.assertEqual(decided(found, [])["label"], "too close")
        self.assertNotIn("lift", verdicts.judged(found))


class Kinds(unittest.TestCase):
    def test_a_skill_with_no_declared_kind_is_incomplete_naming_it(self):
        found = {**summary({"t": case()}, {("t", "with_skill"): [True] * 3, ("t", "without_skill"): [False] * 3},
                           kind=None), **formatted()}
        label = decided(found, [])
        self.assertEqual((label["label"], label["gaps"]),
                         ("incomplete", ["kind: none declared in evals/kinds.json"]))

    def test_an_internal_skill_is_scored_by_its_floors_with_no_lift_and_never_worse_than_before(self):
        found = {**summary({"t": case()}, {("t", "with_skill"): [True] * 3}, kind="internal", own_checks=OWN),
                 **formatted()}
        self.assertEqual((found["runs"], found["baseline_pass_rate"], found["lift"]),
                         ({"t, with_skill": 3}, None, None))  # no without-skill arm, so no baseline and no lift
        self.assertEqual(decided(found, []), {"label": "verified", "gaps": []})
        failed = {**summary({"t": case()}, {("t", "with_skill"): [False] * 3}, kind="internal",
                            own_checks=OWN), **formatted()}
        self.assertEqual(decided(failed, []),
                         {"label": "unsupported", "gaps": ["task pass rate 0% below 90%"]})
        before = {**summary({"t": case()}, {("t", "with_skill"): [True] * 3, ("t", "previous_version"): [True] * 3},
                            kind="internal", previous=True, own_checks=OWN), **formatted()}
        tally = {("t", "with_skill"): {"false_done": 3, "decided": 3, "undecided": 0},
                 ("t", "previous_version"): {"false_done": 0, "decided": 3, "undecided": 0}}
        self.assertEqual(decided(before, [], false_done=tally), {"label": "unsupported", "gaps": [
            "false-done rate 3 of 3 above the previous version's 0 of 3"]})

    def test_an_internal_skill_is_inconclusive_while_a_task_case_runs_none_of_harnesswright_s_own_checks(self):
        gap = ("task case {}: no contract expectation runs one of harnesswright's own checks "
               "(evals/own-checks.json)")
        unchecked = {**summary({"t": case()}, {("t", "with_skill"): [True] * 3}, kind="internal"), **formatted()}
        self.assertEqual(decided(unchecked, []), {"label": "inconclusive", "gaps": [gap.format("t")]})
        only_format = case(expectations=EXPECTATIONS[:2])  # the listed check decides a format expectation only
        cases = {"t": case(), "u": only_format}
        found = {**summary(cases, {(i, "with_skill"): [True] * 3 for i in cases}, kind="internal", own_checks=OWN),
                 **formatted()}
        self.assertEqual(decided(found, []), {"label": "inconclusive", "gaps": [gap.format("u")]})
        team = {**summary(cases, {(i, arm): [arm == "with_skill"] * 3 for i in cases
                                  for arm in ("with_skill", "without_skill")}), **formatted()}
        self.assertEqual(decided(team, []), {"label": "verified", "gaps": []})  # a team skill's lift counts


class TriggerLabel(unittest.TestCase):
    def label(self, outcomes, should=True, unsettled=(), inferred=0):
        cases = {"g": case("trigger", should_trigger=should, split="test")} if outcomes is not None else {}
        scored = {("g", "with_skill"): [bool(o) for o in outcomes or ()]}
        return triggers.label(cases, scored, list(unsettled), inferred, verdicts.THRESHOLDS)

    def test_a_trigger_case_passes_on_half_its_runs_only_when_it_should_trigger(self):
        self.assertEqual(self.label((1, 1, 0, 0))["accuracy"], 1.0)
        self.assertEqual(self.label((1, 1, 0, 0), should=False)["accuracy"], 0.0)  # loaded twice of 4

    def test_the_trigger_label_is_met_on_its_own_and_names_each_gap(self):
        self.assertEqual(self.label((1, 1, 1), inferred=1), {
            "accuracy": 1.0, "threshold": 0.9, "cases": 1, "runs": {"g, with_skill": 3}, "inferred_loads": 1,
            "met": True, "gaps": []})
        self.assertEqual(self.label((0, 0, 0))["gaps"], ["trigger accuracy 0% below 90%"])
        self.assertEqual(self.label(None)["gaps"], ["test trigger cases: none"])
        self.assertEqual(self.label((1, 1))["gaps"], ["g, with_skill: 2 scored run(s), 3 needed"])
        void = ["g, with_skill, run 4: not scored (void)"]
        self.assertEqual((self.label((1, 1, 1), unsettled=void)["met"], self.label((1, 1, 1), unsettled=void)["gaps"]),
                         (False, void))

if __name__ == "__main__":
    unittest.main()
