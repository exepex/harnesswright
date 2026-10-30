"""Seal each host run off from the machine that runs the evals.

A host run must see only its workspace. Without a seal the host inherits the operator's environment,
home and temp folders and can read the whole disk: a Claude Code host started from a Claude Code
session joined that session and loaded its project memory, which named the skill under test and the
repository path, and a baseline run then read the skill from the checkout. A seal gives every run:

- an environment built from an allow list: the system basics below and the variables the adapter
  names in ENV_KEYS, such as the host's API key; nothing else passes;
- a fresh, empty HOME and TMPDIR, deleted after the run, holding only copies of the adapter's
  CREDENTIAL_FILES (the host's sign-in);
- on Linux with `bwrap`, a jail that mounts system folders read-only and the workspace, scratch and
  home folders read-write, with an empty /tmp. The harnesswright checkout, other runs and the
  operator's files are not there to read. Folders the host needs to sign in on a given machine can
  be added read-only with `--host-path`; they are recorded in the results.

Without `bwrap` the run gets the environment and home seal only, and the results say so.
"""

import os
import shutil
import tempfile
from pathlib import Path

# System variables every host may need: the program path, locale, terminal, proxy and CA settings.
BASE_KEYS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ",
             "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "NO_PROXY", "no_proxy",
             "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE",
             "CURL_CA_BUNDLE", "GIT_SSL_CAINFO")
# Variables that name a CA file or folder, which the jail must mount for TLS to work.
CA_KEYS = ("SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE",
           "CURL_CA_BUNDLE", "GIT_SSL_CAINFO")
# System folders mounted read-only in the jail when they exist.
SYSTEM_FOLDERS = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/etc", "/opt", "/nix")
BWRAP = "bwrap"
# Extra folders a host needs read-only to sign in on this machine, set by `--host-path`.
HOST_PATHS = []


def jail_available():
    """True when runs can be jailed here."""
    return shutil.which(BWRAP) is not None


def isolation():
    """What the seal gives on this machine, recorded with every result."""
    if jail_available():
        return "jail: environment allow list, private HOME and TMPDIR, only the workspace mounted"
    return "environment allow list and private HOME and TMPDIR only; the disk stays readable"


def make_home(adapter):
    """A fresh private home folder with copies of the host's credential files."""
    home = Path(tempfile.mkdtemp(prefix="hw-home-"))
    (home / "tmp").mkdir()
    real_home = Path(os.path.expanduser("~"))
    for relative in getattr(adapter, "CREDENTIAL_FILES", ()):
        source = real_home / relative
        if source.is_file():
            target = home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            target.chmod(0o600)
    return home


def environment(adapter, home, scratch=None, source=None):
    """The child's environment: the allow list only, with the private home and temp folders."""
    source = os.environ if source is None else source
    keys = BASE_KEYS + tuple(getattr(adapter, "ENV_KEYS", ()))
    env = {key: source[key] for key in keys if key in source}
    env.update(HOME=str(home), TMPDIR=str(home / "tmp"), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_CACHE_HOME=str((scratch or home) / "cache"))
    return adapter.environment(env)


def jail(command, workspace, home, scratch=None, host_paths=(), env=None):
    """Wrap a host command in a bwrap jail, or return it unchanged when bwrap is missing."""
    if not jail_available():
        return list(command)
    # A host with its own sandbox (Claude Code's is bwrap too) can mount /proc inside the jail only when
    # the jail shows the real /proc. A new user namespace keeps other processes' files out of reach
    # through it (/proc/PID/root).
    args = [BWRAP, "--die-with-parent", "--unshare-user", "--dev-bind", "/proc", "/proc", "--dev", "/dev",
            "--tmpfs", "/tmp"]
    for folder in SYSTEM_FOLDERS:
        path = Path(folder)
        if path.is_symlink():
            args += ["--symlink", os.readlink(path), folder]
        elif path.exists():
            args += ["--ro-bind", folder, folder]
    read_only = [env[key] for key in CA_KEYS if env and env.get(key)] + [str(p) for p in host_paths]
    for path in read_only:
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    for folder in (workspace, home, scratch):
        if folder is not None:
            args += ["--bind", str(folder), str(folder)]
    return args + ["--chdir", str(workspace), "--"] + list(command)
