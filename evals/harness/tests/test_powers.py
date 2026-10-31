"""Powers: the power table is the one statement of what a run may do, and the probe proves the jail gives it."""

import types
import unittest

from helpers import TempCase

import contain
import manifest
import powers

JAIL = contain.available()


class Table(unittest.TestCase):
    def test_each_mode_has_one_answer_for_every_row(self):
        trigger, task = powers.expected("trigger"), powers.expected("task")
        self.assertEqual(list(trigger), list(powers.TABLE))
        self.assertEqual([row for row, must in trigger.items() if must],
                         ["read the world", "read system folders", "write the private home", "write temp",
                          "reach a model host through the gate"])
        self.assertEqual([row for row in powers.TABLE if task[row] != trigger[row]],
                         ["read scratch", "write the world", "write scratch"])
        with self.assertRaises(KeyError):
            powers.expected("interactive")


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Probe(TempCase):
    def run_of(self, mode):
        world = self.tmp / "world"
        world.mkdir(exist_ok=True)
        (world / "README.md").write_text("A notes app.\n")
        host = types.SimpleNamespace(ENV_KEYS=(), CREDENTIAL_FILES=(), MODEL_HOSTS=("model.example.test",),
                                     environment=lambda env: env)
        env = {"PATH": "/usr/bin:/bin"}
        return contain.Containment(host, mode, world, manifest.manifest(world), root=self.tmp / f"run-{mode}",
                                   operator_env=env, operator_home=self.tmp / "operator")

    def test_a_sound_jail_gives_exactly_the_table_and_leaves_the_world_as_it_was(self):
        for mode in ("trigger", "task"):
            with self.subTest(mode=mode):
                run = self.run_of(mode)
                self.assertEqual(powers.probe(run), powers.expected(mode))
                self.assertEqual(manifest.manifest(run.world), run.world_entries)

    def test_a_jail_that_gives_more_than_the_table_is_refused(self):
        run = self.run_of("trigger")
        mounts = run.mounts
        run.mounts = lambda program: [contain.Mount(m.path, "rw", filled=m.filled, scan=m.scan)
                                      if m.path == str(run.world) else m for m in mounts(program)]
        with self.assertRaisesRegex(powers.PowersError, "write the world: works, the table says it must not"):
            powers.probe(run)
        run = self.run_of("task")
        jail = run.jail

        def writable_root(command, program=None):
            args = jail(command, program)
            at = args.index("--remount-ro")
            return args[:at] + args[at + 2:]

        run.jail = writable_root
        with self.assertRaisesRegex(powers.PowersError, "write outside the run: works"):
            powers.probe(run)

    def test_a_jail_without_the_model_hosts_is_refused(self):
        run = self.run_of("task")
        run.hosts = []
        with self.assertRaisesRegex(powers.PowersError, "reach a model host through the gate: does not work"):
            powers.probe(run)


if __name__ == "__main__":
    unittest.main()
