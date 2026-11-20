"""Why an attempt ended: every way an attempt ends writes its reason to the attempt record before the process exits,
a resumed round prints the last attempt's reason, and the label file names every attempt with no recorded reason."""

import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from test_gates import Gated

import endings
import gates
import rounds


def raises(error):
    def step(r):
        raise error
    return step


class Endings(Gated):
    def ended(self):
        return self.attempt()["ended"]["reason"]

    def test_an_attempt_that_passed_every_gate_says_so(self):
        self.planned()
        self.go((("a", lambda r: None), ("b", lambda r: None)))
        self.assertEqual(self.ended(), "passed every gate")

    def test_a_gate_stop_and_a_crash_in_a_gate_write_the_gate_and_its_reason(self):
        self.planned()
        with self.assertRaises(rounds.RoundError):
            self.go((("a", lambda r: None), ("b", raises(rounds.RoundError("broken")))))
        self.assertEqual(self.ended(), "stopped at the b gate: RoundError: broken")
        (self.store / "r1" / "attempts").joinpath(self.attempt_name()).unlink()
        with self.assertRaises(rounds.RoundError):
            self.go((("a", raises(KeyError("lost"))),))
        self.assertEqual(self.ended(), "stopped at the a gate: KeyError: 'lost'")  # its type kept

    def test_an_exit_in_a_gate_writes_its_reason_and_goes_on(self):
        self.planned()
        with self.assertRaises(SystemExit):
            self.go((("a", lambda r: None), ("b", raises(SystemExit(3)))))
        self.assertEqual(self.ended(), "SystemExit during the b gate: 3")

    def test_an_interrupt_and_a_time_limit_s_signal_write_why_as_they_arrive(self):
        self.planned()
        before = signal.getsignal(signal.SIGTERM)
        for number, name in ((signal.SIGINT, "SIGINT"), (signal.SIGTERM, "SIGTERM"), (signal.SIGHUP, "SIGHUP")):
            seen = []

            def killed(r):
                try:
                    os.kill(os.getpid(), number)
                    time.sleep(5)
                finally:  # the cleanup a signal starts: the reason is already in the record
                    seen.append(json.loads(self.only().read_text())["ended"]["reason"])

            with self.assertRaisesRegex(rounds.RoundError, f"^round r1 stopped by {name} during the slow gate$"):
                self.go((("a", lambda r: None), ("slow", killed)))
            self.assertEqual(seen, [f"stopped by {name} during the slow gate"])
            self.assertEqual(self.ended(), seen[0])
            self.assertEqual([g["gate"] for g in self.attempt()["gates"]], ["a"])
            self.only().unlink()
        self.assertIs(signal.getsignal(signal.SIGTERM), before)  # the round's handlers are gone after it

    def test_a_signal_the_process_ignores_stays_ignored(self):
        self.planned()
        before = signal.signal(signal.SIGHUP, signal.SIG_IGN)  # as under nohup
        try:
            seen = []

            def hung_up(r):
                seen.append(signal.getsignal(signal.SIGHUP))
                os.kill(os.getpid(), signal.SIGHUP)

            self.go((("a", hung_up), ("b", lambda r: None)))
            self.assertEqual((seen, self.ended()), ([signal.SIG_IGN], "passed every gate"))
            self.assertIs(signal.getsignal(signal.SIGHUP), signal.SIG_IGN)
        finally:
            signal.signal(signal.SIGHUP, before)

    def test_a_reason_whose_write_failed_can_still_be_written_later(self):
        path, attempt = self.tmp / "gone" / "a1.json", {"gates": []}
        with self.assertRaises(OSError):
            endings.end(path, attempt, "stopped by SIGTERM", str)  # its folder is not there, as on a lost mount
        self.assertFalse(endings.ending(attempt))
        path.parent.mkdir()
        endings.end(path, attempt, "SystemExit during the run gate", str)
        self.assertEqual(json.loads(path.read_text())["ended"]["reason"], "SystemExit during the run gate")
        endings.end(path, attempt, "later", str)  # the first reason written stands
        self.assertEqual(endings.reason(path), "SystemExit during the run gate")

    def test_a_round_process_killed_by_its_time_limit_writes_why_before_it_exits(self):
        self.planned()
        mark = self.tmp / "slow-started"
        script = (f"import sys, time, pathlib\nsys.path.insert(0, {str(Path(gates.__file__).parent)!r})\n"
                  "import gates, rounds\n"
                  f"def slow(r):\n    pathlib.Path({str(mark)!r}).write_text('x')\n    time.sleep(60)\n"
                  f"try:\n    gates.run({str(self.store)!r}, 'r1', repo=pathlib.Path({str(self.repo)!r}), "
                  f"adapters=pathlib.Path({str(self.repo / 'adapters')!r}), gates=(('slow', slow),), seed=7)\n"
                  "except rounds.RoundError as error:\n    sys.exit(f'round: {error}')\n")
        process = subprocess.Popen([sys.executable, "-B", "-c", script], stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 30
        while not mark.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.05)
        process.send_signal(signal.SIGTERM)
        _, err = process.communicate(timeout=30)
        self.assertEqual((process.returncode, err), (1, "round: round r1 stopped by SIGTERM during the slow gate\n"))
        self.assertEqual(self.ended(), "stopped by SIGTERM during the slow gate")

    def test_a_resumed_round_prints_why_its_last_attempt_ended(self):
        self.planned()
        with self.assertRaises(rounds.RoundError):
            self.go((("b", raises(rounds.RoundError("broken"))),))
        first = self.attempt_name()[:-len(".json")]
        self.assertEqual(self.resume(), f"round r1: resuming; the last attempt {first} ended: stopped at the b "
                                        "gate: RoundError: broken\n")
        (self.store / "r1" / "attempts" / "99999999T999999-killed.json").write_text("")  # a SIGKILL: no reason
        self.assertEqual(self.resume(), "round r1: resuming; the last attempt 99999999T999999-killed has no "
                                        "recorded reason\n")

    def resume(self):
        told = io.StringIO()
        with mock.patch.object(gates, "run", return_value={}), contextlib.redirect_stderr(told), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rounds.main(["run", "r1", "--store", str(self.store)]), 0)
        return told.getvalue()

    def test_a_first_attempt_prints_nothing_before_it_starts(self):
        self.assertEqual(endings.resumed(self.store / "r1" / "attempts", "r1"), [])

    def test_every_other_attempt_with_no_recorded_reason_is_named(self):
        folder = self.store / "r1" / "attempts"
        folder.mkdir(parents=True)
        records = {
            "1-ended": {"gates": [{"gate": "run", "passed": True}], "ended": {"reason": "stopped by SIGTERM"}},
            "2-stopped": {"gates": [{"gate": "run", "passed": False, "reason": "RunError: moved"}]},  # before `ended`
            "3-labelled": {"gates": [{"gate": "check", "passed": True}, {"gate": "label", "passed": True}]},
            "4-killed": {"gates": [{"gate": "check", "passed": True}]},
            "6-now": {"gates": []}}
        for name, record in records.items():
            (folder / f"{name}.json").write_text(json.dumps(record))
        (folder / "5-empty.json").write_text("")
        (folder / ".4-killed.json").write_text("{")  # a write a kill cut short, never an attempt
        self.assertEqual(endings.unrecorded(folder, "6-now"), ["4-killed", "5-empty"])
        self.assertEqual([endings.reason(folder / f"{n}.json") for n in ("1-ended", "2-stopped", "3-labelled")],
                         ["stopped by SIGTERM", "stopped at the run gate: RunError: moved", "passed every gate"])

    def only(self):
        [path] = (self.store / "r1" / "attempts").glob("*.json")
        return path

    def attempt_name(self):
        return self.only().name


if __name__ == "__main__":
    unittest.main()
