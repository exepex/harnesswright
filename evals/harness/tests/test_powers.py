"""Powers: the power table is the one statement of what a run may do, and the probe proves the jail gives it."""

import os
import subprocess
import types
import unittest

from helpers import TempCase

import contain
import manifest
import powers
from test_gate import Upstream

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
    def setUp(self):
        super().setUp()
        # Opens tunnels without a network, but not to these hosts.
        self.upstream = Upstream(down=["api.example.test", "off-the-list.invalid"])
        self.addCleanup(self.upstream.close)

    def run_of(self, mode, **kwargs):
        world = self.tmp / "world"
        world.mkdir(exist_ok=True)
        (world / "README.md").write_text("A notes app.\n")
        # The first allowed host is down, so a sound run reaches its model through the second one.
        host = types.SimpleNamespace(ENV_KEYS=(), CREDENTIAL_FILES=(), environment=lambda env: env,
                                     MODEL_HOSTS=("api.example.test", "model.example.test"))
        env = {"PATH": "/usr/bin:/bin", "HTTPS_PROXY": self.upstream.url}
        root = self.tmp / f"run-café-{len(list(self.tmp.glob('run-*')))}"  # a run folder need not be ASCII
        return contain.Containment(host, mode, world, manifest.manifest(world), root=root, operator_env=env,
                                   operator_home=self.tmp / "operator", **kwargs)

    def test_a_sound_jail_gives_exactly_the_table_and_leaves_the_world_as_it_was(self):
        for mode in ("trigger", "task"):
            with self.subTest(mode=mode):
                run = self.run_of(mode)
                os.utime(run.world, (1767607200, 1767607200))
                self.assertEqual(powers.probe(run), powers.expected(mode))
                self.assertEqual(manifest.manifest(run.world), run.world_entries)
                self.assertEqual(os.stat(run.world).st_mtime, 1767607200)  # the probe's write left no trace

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
        run = self.run_of("task")
        jail = run.jail

        def writable_dev(command, program=None):
            args = jail(command, program)
            at = args.index("/dev", args.index("--remount-ro") + 2)
            return args[:at - 1] + args[at + 1:]

        run.jail = writable_dev
        with self.assertRaisesRegex(powers.PowersError, "write outside the run: works"):
            powers.probe(run)
        tool = self.tmp / "tool"  # a folder the operator names, made writable by mistake
        tool.mkdir()
        (tool / "bin").write_text("tool\n")
        run = self.run_of("trigger", host_paths=[tool])
        mounts = run.mounts
        run.mounts = lambda program: [contain.Mount(m.path, "rw", scan=m.scan) if m.path == str(tool) else m
                                      for m in mounts(program)]
        with self.assertRaisesRegex(powers.PowersError, "write outside the run: works"):
            powers.probe(run)
        self.assertEqual(sorted(p.name for p in tool.iterdir()), ["bin"])

    def test_a_jail_with_more_network_than_the_table_is_refused(self):
        run = self.run_of("trigger")
        self.assertFalse(powers.probe(run)["connect directly"])
        jail = run.jail
        # The machine has no route out here, so only the probe's own control shows the shared network.
        run.jail = lambda command, program=None: [a for a in jail(command, program) if a != "--unshare-net"]
        with self.assertRaisesRegex(powers.PowersError, "connect directly: works"):
            powers.probe(run)
        # On a machine with no route out, a failed connection proves nothing: the same fault must still be found.
        shared = ("import sys, types, pathlib\nsys.path[:0] = sys.argv[1:3]\nimport contain, manifest, powers\n"
                  "world = pathlib.Path(sys.argv[3])\nhost = types.SimpleNamespace(ENV_KEYS=(), CREDENTIAL_FILES=(),"
                  " environment=lambda env: env, MODEL_HOSTS=())\n"
                  "run = contain.Containment(host, 'trigger', world, manifest.manifest(world), root=world.parent / "
                  "'no-route', operator_env={'PATH': '/usr/bin:/bin'}, operator_home=world.parent / 'operator')\n"
                  "jail = run.jail\nrun.jail = lambda c, program=None: [a for a in jail(c, program) "
                  "if a != '--unshare-net']\ntry:\n    powers.probe(run)\nexcept powers.PowersError as error:\n"
                  "    print(error)\n")
        here = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(["bwrap", "--dev-bind", "/", "/", "--unshare-net", contain.PYTHON, "-B", "-c",
                                 shared, os.path.dirname(here), here, str(run.world)],
                                capture_output=True, text=True, timeout=120)
        self.assertIn("connect directly: works", result.stdout, result.stderr)
        run = self.run_of("task")
        run.hosts = run.hosts + ["off-the-list.invalid"]  # passed on, though upstream answers 502 for it
        with self.assertRaisesRegex(powers.PowersError, "reach a host off the allow list: works"):
            powers.probe(run)

    def test_a_model_host_counts_only_when_the_gate_opens_a_tunnel(self):
        for change in ({"hosts": []}, {"upstream": "http://127.0.0.1:9"}):  # no model host; the gate answers 502
            run = self.run_of("task")
            for key, value in change.items():
                setattr(run, key, value)
            with self.subTest(change=change), self.assertRaisesRegex(
                    powers.PowersError, "reach a model host through the gate: does not work"):
                powers.probe(run)


if __name__ == "__main__":
    unittest.main()
