"""Containment: a run sees exactly its one list of mounts, and the audit proves it from inside the jail."""

import os
import subprocess
import types
import unittest

from helpers import TempCase

import audit
import cases
import contain
import manifest

JAIL = contain.available()


def adapter(**extra):
    found = types.SimpleNamespace(ENV_KEYS=("HOST_API_KEY",), CREDENTIAL_FILES=(".host/auth.json",),
                                  environment=lambda env: env)
    for key, value in extra.items():
        setattr(found, key, value)
    return found


class Setup(TempCase):
    """What is built before any jail: the environment, the home and the list. No bwrap needed."""

    def run_of(self, mode="task", host=None, **kwargs):
        world = self.tmp / "world"
        world.mkdir(exist_ok=True)
        (world / "README.md").write_text("A notes app.\n")
        operator = self.tmp / "operator"
        (operator / ".host").mkdir(parents=True, exist_ok=True)
        if not (operator / ".host" / "auth.json").exists():
            (operator / ".host" / "auth.json").write_text('{"token": "decoy-credential-value"}\n')
        env = {"PATH": "/usr/bin:/bin", "HOST_API_KEY": "decoy-api-key", "SESSION_TOKEN": "decoy-session",
               "GIT_DIR": "/elsewhere"}
        kwargs.setdefault("root", self.tmp / f"run-{len(list(self.tmp.iterdir()))}")
        return contain.Containment(host or adapter(), mode, world, manifest.manifest(world), operator_env=env,
                                   operator_home=operator, **kwargs)

    def test_the_environment_is_the_allow_list_and_the_run_folders(self):
        run = self.run_of()
        self.assertEqual(sorted(run.env), sorted(["PATH", "HOST_API_KEY"] + list(contain.RUN_KEYS)))
        self.assertEqual(run.env["HOME"], str(run.home))
        self.assertEqual(run.env["TMPDIR"], str(run.scratch / "tmp"))
        with self.assertRaisesRegex(contain.ContainmentError, "outside the allow list: \\['EXTRA'\\]"):
            self.run_of(host=adapter(environment=lambda env: {**env, "EXTRA": "1"}))

    def test_the_home_holds_only_tmp_and_the_credential_copies(self):
        run = self.run_of()
        self.assertEqual(manifest.manifest(run.home), run.home_entries)
        self.assertEqual(sorted(run.home_entries), [".host", ".host/auth.json", "tmp"])
        self.assertEqual(os.stat(run.home / ".host" / "auth.json").st_mode & 0o777, 0o600)
        (self.tmp / "operator" / ".host" / "auth.json").unlink()
        (self.tmp / "operator" / ".host" / "auth.json").symlink_to("/etc/hostname")
        with self.assertRaisesRegex(contain.ContainmentError, "not a regular file"):
            self.run_of()

    def test_the_list_never_holds_the_repository_or_the_operator_home(self):
        run = self.run_of()
        paths = [m.path for m in run.mounts("python3")]
        for path in ("/etc", "/home", "/root", "/opt", str(self.tmp / "operator")):
            self.assertNotIn(path, paths)
        self.assertNotIn("/etc/gitconfig", paths)
        for host_path in (cases.REPO / "evals", cases.REPO.parent, self.tmp):
            with self.subTest(host_path=host_path), self.assertRaisesRegex(contain.ContainmentError, "may not mount"):
                self.run_of(host_paths=[host_path]).mounts("python3")
        with self.assertRaisesRegex(contain.ContainmentError, "which the harness fills"):
            self.run_of(host_paths=[self.tmp / "world"]).mounts("python3")

    def test_the_view_rule_finds_what_the_list_does_not_hold(self):
        problems = []
        audit.view({"mounts": [{"path": "/usr", "how": "ro", "source": None, "filled": False, "scan": False}]},
                   problems)
        self.assertTrue(problems)
        self.assertIn("/ holds", problems[0])
        self.assertIn("'etc'", problems[0])


@unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
class Jail(Setup):
    """The audit inside a real jail. Planted faults use a decoy operator home, never the real one."""

    def inside(self, run, *command):
        return subprocess.run(run.jail(list(command)), capture_output=True, text=True, env=run.env, timeout=60)

    def test_a_sound_jail_passes_and_shows_only_the_list(self):
        for mode in ("trigger", "task"):
            with self.subTest(mode=mode):
                run = self.run_of(mode)
                report = run.audit("python3")
                self.assertEqual(report["problems"], [])
                listing = self.inside(run, "/bin/ls", "-a", "/", "/etc", str(self.tmp)).stdout.split()
                for hidden in ("home", "root", "opt", "gitconfig", "operator"):
                    self.assertNotIn(hidden, listing)

    def test_canaries_outside_are_unseen_and_inside_are_found(self):
        outside = contain.plant_canaries([self.tmp / "operator", self.tmp / "other-run"])
        run = self.run_of(tokens=outside)
        self.assertEqual(run.audit("python3")["problems"], [])
        for path in outside.values():
            self.assertNotEqual(self.inside(run, "/bin/cat", path).returncode, 0)
        inside = contain.plant_canaries([self.tmp / "world" / "docs"])
        world = self.tmp / "world"
        run = self.run_of(tokens=list(outside) + list(inside))
        run.world_entries = manifest.manifest(world)
        with self.assertRaisesRegex(contain.ContainmentError, "a canary token is in .*world/docs"):
            run.audit("python3")

    def test_a_canary_in_a_credential_file_is_found(self):
        (self.tmp / "operator" / ".host").mkdir(parents=True)
        (self.tmp / "operator" / ".host" / "auth.json").write_text('{"token": "HWCANARY-0123456789abcdef"}\n')
        run = self.run_of(tokens=["HWCANARY-0123456789abcdef"])
        with self.assertRaisesRegex(contain.ContainmentError, "a canary token is in .*auth.json"):
            run.audit("python3")

    def test_a_world_that_is_not_the_proved_arm_is_refused(self):
        run = self.run_of()
        (self.tmp / "world" / "notes.md").write_text("Added after the proof.\n")
        with self.assertRaisesRegex(contain.ContainmentError, "world does not hold exactly"):
            run.audit("python3")

    def test_the_jail_environment_is_exactly_the_one_built(self):
        run = self.run_of()
        names = self.inside(run, "/usr/bin/env").stdout
        self.assertNotIn("SESSION_TOKEN", names)
        self.assertNotIn("GIT_DIR", names)
        jail = run.jail
        run.jail = lambda command, program=None: jail(command, program)[:1] + ["--setenv", "LEAKED", "1"] + \
            jail(command, program)[1:]
        with self.assertRaisesRegex(contain.ContainmentError, "environment keys"):
            run.audit("python3")

    def test_a_trigger_run_cannot_change_its_world(self):
        run = self.run_of("trigger")
        self.assertNotEqual(self.inside(run, "/usr/bin/touch", "new.md").returncode, 0)
        task = self.run_of("task")
        self.assertEqual(self.inside(task, "/usr/bin/touch", "new.md").returncode, 0)


if __name__ == "__main__":
    unittest.main()
