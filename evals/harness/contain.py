"""Containment: what a run can see (doc 11, Containment).

One rule: a run sees exactly one list of mounts, and nothing else. `Containment.mounts` builds the list once: the
system folders and the `/etc` entries in `ETC` (read-only), the host's install and CA files (read-only), the world
(read-only in trigger runs), a fresh home, a scratch folder in task runs, an empty `/tmp`, a fresh `/proc` and a
minimal `/dev`, and the gate's socket. The jail has no network of its own: every connection goes through the gate
(`gate.py`), which allows only the host's model hosts. The jail is built from the list, and `audit.py` checks the
jail against the same list from inside it before the host starts. Any problem raises ContainmentError: the run is
void and the round stops. The environment is built from an allow list (`BASE_KEYS`, the adapter's `ENV_KEYS`, its
fixed `RUN_ENV` and the run's folders), never inherited.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import gate
import manifest
from cases import REPO

BWRAP = "bwrap"
# System variables every host may need: the program path, locale, terminal and CA settings.
BASE_KEYS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ",
             "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE",
             "CURL_CA_BUNDLE", "GIT_SSL_CAINFO")
# Variables that name a CA file or folder, which the jail mounts read-only so TLS works.
CA_KEYS = ("SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
           "GIT_SSL_CAINFO")
# Set by the harness: the run's own folders (PWD is the world, as the jail sets it) and the gate as the only proxy.
PROXY_KEYS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
RUN_KEYS = ("HOME", "TMPDIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "PWD") + PROXY_KEYS
GATE = "/run/gate"  # where the gate's socket is inside the jail
PYTHON = "/usr/bin/python3"
SYSTEM = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32")
ETC = ("alternatives", "ca-certificates", "ca-certificates.conf", "crypto-policies", "gai.conf", "group",
       "host.conf", "hostname", "hosts", "ld.so.cache", "ld.so.conf", "ld.so.conf.d", "localtime", "mime.types",
       "nsswitch.conf", "os-release", "passwd", "pki", "protocols", "resolv.conf", "services", "ssl", "terminfo",
       "timezone")
TOKEN_PREFIX = "HWCANARY"
AUDIT = Path(__file__).resolve().parent / "audit.py"
MANIFEST = Path(manifest.__file__).resolve()


class ContainmentError(RuntimeError):
    """The containment cannot be set up or did not hold. The run is void and the round stops."""


def available():
    """Why this machine cannot contain runs, or None. Without a passing containment there are no labels."""
    if not sys.platform.startswith("linux"):
        return "the default containment needs Linux"
    if shutil.which(BWRAP) is None:
        return "bwrap is not installed (install bubblewrap)"
    return None


def new_token():
    return f"{TOKEN_PREFIX}-{secrets.token_hex(8)}"


class Mount:
    """One entry of the list: `how` is `ro`, `rw`, `link` (a symlink to `source`), `socket` (the gate's socket at
    `source`), `tmpfs`, `proc` or `dev`."""

    def __init__(self, path, how, source=None, filled=None, scan=False):
        self.path, self.how, self.source = str(path), how, source
        self.filled = filled  # the manifest the mount must hold, for a folder the harness fills
        self.scan = scan  # scanned for canary tokens

    def args(self):
        if self.how in ("ro", "rw", "socket"):
            return ["--bind" if self.how == "rw" else "--ro-bind", self.source or self.path, self.path]
        if self.how == "link":
            return ["--symlink", self.source, self.path]
        return {"tmpfs": ["--tmpfs"], "proc": ["--proc"], "dev": ["--dev"]}[self.how] + [self.path]

    def spec(self):
        return {"path": self.path, "how": self.how, "source": self.source if self.how == "link" else None,
                "filled": self.filled is not None, "scan": self.scan}


class Containment:
    """The folders, environment and jail of one run, under `root`.

    `operator_env` and `operator_home` are where sign-in values and credential files come from: the real ones in a
    round, a decoy in fault tests. `world_entries` is the manifest of the proved arm. `tokens` are the canary tokens
    planted for the round. `host_paths` are extra folders the host needs to sign in on this machine.
    """

    def __init__(self, adapter, mode, world, world_entries, root, operator_env=None, operator_home=None,
                 host_paths=(), tokens=()):
        if mode not in ("trigger", "task"):
            raise ValueError(f"unknown mode: {mode}")
        self.adapter, self.mode, self.world = adapter, mode, Path(world).resolve()
        self.world_entries = dict(world_entries)
        self.root = Path(root).resolve()
        self.home = self.root / "home"
        self.scratch = self.root / "scratch" if mode == "task" else None
        self.operator_env = dict(os.environ if operator_env is None else operator_env)
        self.operator_home = Path(operator_home or os.path.expanduser("~"))
        self.host_paths = [Path(p) for p in host_paths]
        self.tokens = sorted(tokens)
        self.socket = self.root / "gate.sock"
        self.upstream = next((self.operator_env[k] for k in ("HTTPS_PROXY", "https_proxy")
                              if self.operator_env.get(k)), None)
        self.hosts = self._hosts()
        self.home_entries = self._make_home()
        self.scratch_entries = self._make_scratch()
        self.env = self._environment()

    def _hosts(self):
        """The gate's allow list: the adapter's MODEL_HOSTS, and the host of every URL the adapter's ENV_KEYS pass
        on (such as a base URL), since that is where the operator points the host's model."""
        names = list(getattr(self.adapter, "MODEL_HOSTS", ()))
        names += [self.operator_env[k] for k in getattr(self.adapter, "ENV_KEYS", ())
                  if "://" in self.operator_env.get(k, "")]
        try:
            return gate.allowed_hosts(names)
        except ValueError as error:
            raise ContainmentError(f"the gate's allow list: {error}") from None

    def gate(self):
        """The run's gate, a context manager. Every jail of this run runs inside it."""
        try:
            return gate.Gate(self.socket, self.hosts, self.upstream)
        except ValueError as error:
            raise ContainmentError(f"the gate cannot start: {error}") from None

    def _make_home(self):
        """A fresh home holding `tmp/` and copies of the adapter's CREDENTIAL_FILES that exist as regular files."""
        (self.home / "tmp").mkdir(parents=True)
        entries = {"tmp": "dir"}
        for relative in getattr(self.adapter, "CREDENTIAL_FILES", ()):
            source = self.operator_home / relative
            if not os.path.lexists(source):
                continue
            if manifest.kind(manifest.entry(source)) != "file":
                raise ContainmentError(f"credential file {relative} is not a regular file")
            target = self.home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            target.chmod(0o600)
            for parent in PurePosixPath(relative).parents:
                if str(parent) != ".":
                    entries[str(parent)] = "dir"
            entries[relative] = manifest.entry(target)
        return entries

    def _make_scratch(self):
        if self.scratch is None:
            return None
        for name in ("tmp", "cache"):
            (self.scratch / name).mkdir(parents=True)
        return {"tmp": "dir", "cache": "dir"}

    def _environment(self):
        keys = BASE_KEYS + tuple(getattr(self.adapter, "ENV_KEYS", ()))
        env = {key: self.operator_env[key] for key in keys if key in self.operator_env}
        env.update({key: gate.ADDRESS for key in PROXY_KEYS})
        env.update(HOME=str(self.home), PWD=str(self.world), TMPDIR=str((self.scratch or self.home) / "tmp"),
                   XDG_CONFIG_HOME=str(self.home / ".config"),
                   XDG_CACHE_HOME=str(self.scratch / "cache" if self.scratch else self.home / ".cache"))
        fixed = dict(getattr(self.adapter, "RUN_ENV", {}))  # set by the adapter, never taken from the operator
        env.update(fixed)
        env = dict(self.adapter.environment(env))
        extra = sorted(set(env) - set(keys) - set(RUN_KEYS) - set(fixed))
        if extra:
            raise ContainmentError(f"the adapter added variables outside the allow list: {extra}")
        return env

    def mounts(self, program):
        """The one list of what a run sees, for a run of `program`."""
        found = [Mount("/tmp", "tmpfs"), Mount("/proc", "proc"), Mount("/dev", "dev"), Mount("/dev/shm", "tmpfs"),
                 Mount(GATE, "socket", source=str(self.socket))]
        for folder in SYSTEM:
            if os.path.islink(folder):
                found.append(Mount(folder, "link", source=os.readlink(folder)))
            elif os.path.isdir(folder):
                found.append(Mount(folder, "ro"))
        found += [Mount(f"/etc/{name}", "ro") for name in ETC if os.path.exists(f"/etc/{name}")]
        outside = [Path(self.env[key]) for key in CA_KEYS if self.env.get(key)]
        outside += self.host_paths
        named = [Mount(path, "ro", scan=True) for path in dict.fromkeys(outside) if path.exists()]
        found += named + self._install(program)
        found.append(Mount(self.world, "rw" if self.mode == "task" else "ro", filled=self.world_entries, scan=True))
        found.append(Mount(self.home, "rw", filled=self.home_entries, scan=True))
        if self.scratch:
            found.append(Mount(self.scratch, "rw", filled=self.scratch_entries, scan=True))
        self._refuse_overlaps(found, named)
        return found

    def _install(self, program):
        """The host's install, for `program` on the run's PATH and after links: the folder above its `bin` folder
        (such as a node install), else its own folder. A program the operator names in `host_paths` needs no more."""
        found = shutil.which(program, path=self.env.get("PATH"))
        if found is None:
            return []
        named, mounts = [p.resolve() for p in self.host_paths], []
        for p in dict.fromkeys((Path(found).absolute(), Path(found).resolve())):  # the PATH entry, then its target
            if not any(p.is_relative_to(f) for f in SYSTEM) and not any(p.resolve().is_relative_to(n) for n in named):
                mounts.append(Mount(p.parent.parent if p.parent.name == "bin" else p.parent, "ro", scan=True))
        return mounts

    def _refuse_overlaps(self, mounts, named):
        """The one check of where mounts may be, on resolved paths: never in or holding the repository, never holding
        the operator's home, in it only when the operator names it or the harness fills it (a folder found there, such
        as `~/.local`, holds the operator's files), and never inside a mount the harness fills."""
        repo, home = REPO.resolve(), self.operator_home.resolve()
        bound = [m for m in mounts if m.how in ("ro", "rw", "socket")]
        for mount in bound:
            path = Path(mount.source or mount.path).resolve()
            if path.is_relative_to(repo) or repo.is_relative_to(path) or home.is_relative_to(path):
                raise ContainmentError(f"a run may not mount {mount.path}: it holds or is inside the repository "
                                       "or the operator's home")
            made = mount.filled is not None or mount.how == "socket"  # by the harness, so it holds nothing else
            if path.is_relative_to(home) and mount not in named and not made:
                raise ContainmentError(f"{mount.path} is in the operator's home: name the files and folders the host "
                                       "needs in host_paths")
            for other in bound:
                if other is not mount and other.filled is not None and path.is_relative_to(Path(other.path)):
                    raise ContainmentError(f"{mount.path} lies inside {other.path}, which the harness fills")

    def jail(self, command, program=None):
        """`command` wrapped in this run's jail. `program` is the host whose install is mounted (default the
        command's own program), so the audit runs with exactly the host's mounts."""
        reason = available()
        if reason:
            raise ContainmentError(reason)
        # Its own user, process, IPC, host name, cgroup and network namespaces. The network holds only loopback, where
        # the forwarder passes connections to the gate, so the gate's allow list is the only way out (doc 11, Powers).
        args = [BWRAP, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc",
                "--unshare-uts", "--unshare-cgroup-try", "--unshare-net"]
        for mount in self.mounts(program or command[0]):
            args += mount.args()
        # The folders the jail creates, and /dev, are read-only, so a run writes only what the list makes writable.
        args += ["--remount-ro", "/", "--remount-ro", "/dev", "--chdir", str(self.world), "--"]
        return args + [PYTHON, "-I", "-c", gate.FORWARDER, GATE] + list(command)

    def audit(self, program):
        """Run the visibility audit in this run's jail, for a run of `program`. Return its report, or raise
        ContainmentError with every problem it found."""
        mounts = self.mounts(program)
        spec = {"mounts": [m.spec() for m in mounts], "tokens": self.tokens}
        # The audit's code goes in as one program text, so no harness file is mounted for it.
        source = MANIFEST.read_text() + "\n" + AUDIT.read_text()
        command = self.jail([PYTHON, "-I", "-c", source], program=program)
        with self.gate():
            result = subprocess.run(command, input=json.dumps(spec), capture_output=True, text=True, env=self.env,
                                    timeout=600)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise ContainmentError(f"the audit did not run: {result.stderr.strip()[-400:]}") from None
        problems = list(report["problems"])
        if sorted(report["env"]) != sorted(self.env):
            problems.append(f"the jail's environment keys {sorted(report['env'])} are not the ones built "
                            f"{sorted(self.env)}")
        for mount in mounts:
            if mount.filled is not None and report["filled"].get(mount.path) != manifest.digest(mount.filled):
                problems.append(f"{mount.path} does not hold exactly what the harness put there")
        if problems:
            raise ContainmentError("; ".join(problems))
        return report


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
