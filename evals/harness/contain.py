"""Containment: what a run can see. A run sees only its world, its own folders, read-only system folders and its
host's install, and the visibility audit proves it inside the same jail before the host starts (doc 11).

Every run gets, under its own root folder:

- `home/`: a fresh private HOME holding only copies of the adapter's CREDENTIAL_FILES;
- `scratch/` (task runs): a writable folder outside the world, holding the run's temp and cache folders.

The environment is built from an allow list (`seal.BASE_KEYS` and the adapter's ENV_KEYS) and never inherited.
In the jail, system folders are read-only, host machine-config folders are masked empty, `/tmp` is an empty
private folder, and the world is read-only in trigger runs. Nothing else is mounted.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))
import seal  # noqa: E402

from cases import REPO, tree, tree_hash  # noqa: E402

AUDIT_SOURCE = (Path(__file__).resolve().parent / "audit.py").read_text()
# Machine-wide host config folders a run must never read: they can hold managed settings, skills or rules.
HOST_CONFIG = ("/etc/codex", "/etc/claude-code")
TOKEN_PREFIX = "HWCANARY"
RUN_KEYS = ("HOME", "TMPDIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "PWD", "LC_CTYPE")


class ContainmentError(RuntimeError):
    """The containment cannot be set up or did not hold. The run is voided and the round stops."""


def available():
    """Why this machine cannot contain runs, or None. Without a passing containment there are no labels."""
    if not sys.platform.startswith("linux"):
        return "the default containment needs Linux"
    if shutil.which(seal.BWRAP) is None:
        return "bwrap is not installed (install bubblewrap)"
    return None


def new_token():
    return f"{TOKEN_PREFIX}-{secrets.token_hex(8)}"


class Containment:
    """The folders, environment and jail of one run.

    `operator_env` and `operator_home` are where sign-in values and credential files come from: the real ones in
    a round, a decoy in fault tests. `masks` hides more paths, such as a Python interpreter in a skill fault.
    """

    def __init__(self, adapter, root, mode, world, operator_env=None, operator_home=None, masks=(),
                 host_paths=(), forbidden=(), canaries=None, world_sha256=None):
        if mode not in ("trigger", "task"):
            raise ValueError(f"unknown mode: {mode}")
        self.adapter, self.mode, self.world = adapter, mode, Path(world)
        self.root = Path(root)
        self.home = self.root / "home"
        self.scratch = self.root / "scratch" if mode == "task" else None
        for folder in (self.home, self.home / "tmp", self.scratch):
            if folder is not None:
                folder.mkdir(parents=True, exist_ok=True)
        if self.scratch:
            (self.scratch / "tmp").mkdir(exist_ok=True)
            (self.scratch / "cache").mkdir(exist_ok=True)
        self.operator_env = dict(os.environ if operator_env is None else operator_env)
        self.operator_home = Path(operator_home or os.path.expanduser("~"))
        self.masks = tuple(HOST_CONFIG) + tuple(masks)
        self.host_paths = tuple(str(p) for p in host_paths)
        self.forbidden = tuple(str(p) for p in forbidden) + (str(REPO), str(self.operator_home))
        self.canaries = dict(canaries or {})  # {token: planted file}
        self.world_sha256 = world_sha256  # the built arm's hash; None measures the world as it is now
        self.credentials = self._copy_credentials()
        self.prepared = []  # files the adapter wrote into the home before the run, such as denied-command rules
        self.env = self._environment()
        # The credentials as given, kept for redaction even if the host later refreshes or rewrites its files.
        self.initial_secrets = self._read_secrets()

    def _copy_credentials(self):
        copied = []
        for relative in getattr(self.adapter, "CREDENTIAL_FILES", ()):
            source = self.operator_home / relative
            if source.is_file():
                target = self.home / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                target.chmod(0o600)
                copied.append(relative)
        return copied

    def _environment(self):
        keys = seal.BASE_KEYS + tuple(getattr(self.adapter, "ENV_KEYS", ()))
        env = {key: self.operator_env[key] for key in keys if key in self.operator_env}
        temp = (self.scratch or self.home) / "tmp"
        cache = self.scratch / "cache" if self.scratch else self.home / ".cache"
        env.update(HOME=str(self.home), TMPDIR=str(temp), XDG_CONFIG_HOME=str(self.home / ".config"),
                   XDG_CACHE_HOME=str(cache))
        env.update(getattr(self.adapter, "SEALED_ENV", {}))
        return self.adapter.environment(env)

    def secrets(self):
        """Every credential value a bundle must never hold: sign-in variables and strings in credential files,
        both as they were given to the run and as they are now."""
        return sorted(set(self.initial_secrets) | set(self._read_secrets()), key=len, reverse=True)

    def _read_secrets(self):
        values = [self.env[key] for key in getattr(self.adapter, "ENV_KEYS", ()) if len(self.env.get(key, "")) >= 8]
        # A proxy variable can carry a user and password: the whole value and its user part are credentials.
        for key in seal.BASE_KEYS:
            if "proxy" in key.lower() and self.env.get(key):
                values += _proxy_secrets(self.env[key])
        for relative in self.credentials:
            try:
                text = (self.home / relative).read_text()
            except OSError:
                continue  # the host removed it; the values it held at the start are kept in initial_secrets
            try:
                values += [v for v in _strings(json.loads(text)) if len(v) >= 16]
            except json.JSONDecodeError:
                values.append(text.strip())
        return sorted(set(v for v in values if v), key=len, reverse=True)

    def mounts(self, program):
        """(read-only paths, writable paths) besides the system folders."""
        read_only = [self.env[key] for key in seal.CA_KEYS if self.env.get(key)]
        read_only += list(self.host_paths) + [str(p) for p in seal.host_install(program)]
        writable = [str(self.home)] + ([str(self.scratch)] if self.scratch else [])
        if self.mode == "task":
            writable.append(str(self.world))
        else:
            read_only.append(str(self.world))
        # Neither a folder inside the repository nor one that holds it, such as its parent or /home.
        repo = REPO.resolve()
        inside = [p for p in read_only + writable
                  if Path(p).resolve().is_relative_to(repo) or repo.is_relative_to(Path(p).resolve())]
        if inside:
            raise ContainmentError(f"a run may not mount anything of this repository: {inside}")
        return [p for p in read_only if Path(p).exists()], writable

    def jail(self, command, program=None):
        """`command` wrapped in the bwrap jail of this run. `program` is the host whose install is mounted
        (default the command's own program), so the audit runs with exactly the host's mounts."""
        reason = available()
        if reason:
            raise ContainmentError(reason)
        args = [seal.BWRAP, "--die-with-parent", "--unshare-user", "--dev-bind", "/proc", "/proc",
                "--dev", "/dev", "--tmpfs", "/tmp"]
        for folder in seal.SYSTEM_FOLDERS:
            path = Path(folder)
            if path.is_symlink():
                args += ["--symlink", os.readlink(path), folder]
            elif path.exists():
                args += ["--ro-bind", folder, folder]
        for mask in self.masks:
            if os.path.isdir(mask):
                args += ["--tmpfs", mask]
            elif os.path.lexists(mask):
                args += ["--ro-bind", "/dev/null", mask]
        read_only, writable = self.mounts(program or command[0])
        for path in read_only:
            args += ["--ro-bind", path, path]
        for path in writable:
            args += ["--bind", path, path]
        return args + ["--chdir", str(self.world), "--"] + list(command)

    def audit_spec(self, program):
        read_only, writable = self.mounts(program)
        mounted = read_only + writable
        root_allowed = {"proc", "dev", "tmp"} | {Path(f).name for f in seal.SYSTEM_FOLDERS if os.path.lexists(f)}
        root_allowed |= {Path(p).parts[1] for p in mounted if len(Path(p).parts) > 1}
        # A folder above a mount that is not itself mounted, such as /tmp or /root, may hold only the way to it.
        only = {}
        system = [Path(f) for f in seal.SYSTEM_FOLDERS]
        for mount in map(Path, mounted):
            for parent in mount.parents:
                if parent == Path("/") or any(parent.is_relative_to(f) for f in system) or str(parent) in mounted:
                    continue
                only.setdefault(str(parent), set()).add(mount.relative_to(parent).parts[0])
        only = {folder: sorted(names) for folder, names in only.items()}
        only[str(self.home)] = sorted({Path(r).parts[0] for r in self.credentials + self.prepared} | {"tmp"})
        # The allow list comes from the policy, not from the environment built: the system basics, the adapter's
        # sign-in keys and fixed values, the run's folders, PWD (set by bwrap) and LC_CTYPE (set by Python in a
        # C locale, PEP 538).
        allowed = set(seal.BASE_KEYS) | set(getattr(self.adapter, "ENV_KEYS", ())) | \
            set(getattr(self.adapter, "SEALED_ENV", {})) | set(RUN_KEYS)
        return {"env_allowed": sorted(allowed), "root_allowed": sorted(root_allowed),
                "forbidden": [p for p in self.forbidden if not any(_overlaps(p, m) for m in mounted)],
                "masked": [m for m in self.masks if os.path.lexists(m)],
                "only_entries": only,
                "world": str(self.world),
                "world_sha256": self.world_sha256 or tree_hash(tree(self.world, skip=(".git",))),
                "scan": [p for p in mounted if Path(p).is_dir()],
                "tokens": sorted(self.canaries), "canary_files": sorted(self.canaries.values())}

    def audit(self, program):
        """Run the visibility audit inside this jail. Return its report; raise ContainmentError on any problem."""
        python = shutil.which("python3", path="/usr/bin:/bin") or "/usr/bin/python3"
        command = self.jail([python, "-I", "-c", AUDIT_SOURCE], program=program)
        result = subprocess.run(command, input=json.dumps(self.audit_spec(program)), capture_output=True,
                                text=True, env=self.env, timeout=120)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise ContainmentError(f"the audit did not run: {result.stderr.strip()[-400:]}") from None
        if report["problems"]:
            raise ContainmentError("; ".join(report["problems"]))
        return report


def _overlaps(path, mount):
    path, mount = Path(path), Path(mount)
    return path == mount or path.is_relative_to(mount) or mount.is_relative_to(path)


def _proxy_secrets(value):
    """The credential parts of a proxy URL: the whole value, its user part and its password, raw and decoded."""
    try:
        parts = urlsplit(value if "://" in value else "http://" + value)
        user, password = parts.username, parts.password
    except ValueError:
        return [value]
    if user is None and password is None:
        return []
    userinfo = parts.netloc.rpartition("@")[0]
    found = [value, userinfo] + [v for v in (password, user) if v and len(v) >= 4]
    return found + [unquote(v) for v in found]


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def plant_canaries(places):
    """Write one fresh canary token into each folder in `places`. Return {token: file}."""
    planted = {}
    for place in places:
        token = new_token()
        path = Path(place) / f".hw-canary-{token[-6:]}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{token}\n")
        planted[token] = str(path)
    return planted


def remove_canaries(planted):
    for path in planted.values():
        Path(path).unlink(missing_ok=True)
