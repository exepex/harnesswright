"""Grader faults: a grader that writes to its folder or reads outside it is caught on the fake host in the jail
(every place is run in test_faults), and a jail made to let it through is reported as a miss."""

import unittest
from unittest import mock

from test_faults import Fake
from test_host import JAIL

import contain
import faults

MOUNTS = contain.Containment.mounts


def world_writable(self, program):
    """A jail that mounts a trigger run's world read and write."""
    return [contain.Mount(m.path, "rw", filled=m.filled, scan=m.scan) if m.path == str(self.world) else m
            for m in MOUNTS(self, program)]


def temp_shown(self, program):
    """A jail that shows the machine's temporary folder, where grader folders are made, in place of a fresh one."""
    return [contain.Mount(m.path, "rw") if m.path == "/tmp" else m for m in MOUNTS(self, program)]


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Missed(Fake):
    def test_a_jail_that_lets_a_grader_out_is_a_miss(self):
        setup = self.setup_of()
        entry = next(e for e in faults.load() if e["id"] == "folder")
        for place, mounts, reason in (("writes", world_writable, "changed its folder"),
                                      ("writes", temp_shown, "beside it"),
                                      ("reads", temp_shown, "can find|a canary token reached")):
            with self.subTest(place=place, mounts=mounts.__name__), \
                    mock.patch.object(contain.Containment, "mounts", mounts):
                outcome = faults.run(entry, setup, seed=0, place=place)
                self.assertFalse(outcome["caught"])
                self.assertRegex(outcome["reason"], reason)


if __name__ == "__main__":
    unittest.main()
