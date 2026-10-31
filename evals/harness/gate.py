"""The network gate: the one way out of a run's jail (doc 11, Powers).

The jail has no network of its own. A run reaches the network only through the gate, a small HTTPS proxy that runs
outside the jail and listens on a unix socket inside the run's folder. It allows one request kind, `CONNECT
host:443`, and only to the hosts on one allow list: the host's model endpoints. Everything else is refused with
`403`, and every request is recorded with its answer. The gate never reads the encrypted traffic it passes on.

Inside the jail, `FORWARDER` runs first: it listens on `127.0.0.1:PORT`, passes each connection to the gate's
socket, and starts the host with `HTTPS_PROXY` pointing at it. When the operator's machine reaches the internet
through its own proxy, the gate goes through that proxy, so its address and any password in it never enter the
jail.

Standard library only.
"""

import base64
import os
import re
import socket
import socketserver
import threading
from urllib.parse import unquote, urlsplit

PORT = 3128
ADDRESS = f"http://127.0.0.1:{PORT}"  # the proxy every program in the jail is given
# A DNS name: lower-case labels, the last one starting with a letter as a top-level domain does. No spelling of
# an IP address (dotted, hex, octal or short) can match, so the gate only ever resolves a name.
HOST_PATTERN = re.compile(r"([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]([a-z0-9-]*[a-z0-9])?")

# Runs inside the jail as `python3 -I -c FORWARDER GATE_SOCKET COMMAND...`.
FORWARDER = r'''
import os, socket, sys, threading

def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

def serve(listener, path):
    while True:
        client, _ = listener.accept()
        gate = socket.socket(socket.AF_UNIX)
        try:
            gate.connect(path)
        except OSError:
            client.close()
            continue
        for a, b in ((client, gate), (gate, client)):
            threading.Thread(target=pipe, args=(a, b), daemon=True).start()

listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(("127.0.0.1", PORT))
listener.listen(64)
# The host gets the environment the jail was started with, before Python changed any of it (such as the locale).
with open("/proc/self/environ", "rb") as handle:
    env = dict(item.split(b"=", 1) for item in handle.read().split(b"\0") if item)
child = os.fork()
if child == 0:
    listener.close()
    os.execvpe(sys.argv[2], sys.argv[2:], env)
threading.Thread(target=serve, args=(listener, sys.argv[1]), daemon=True).start()  # after the fork, never before
_, status = os.waitpid(child, 0)
sys.exit(os.waitstatus_to_exitcode(status))
'''.replace("PORT", str(PORT))


def allowed_hosts(names):
    """The allow list from host names and URLs (such as a base URL the adapter passes on). Raise ValueError for a
    name that is not a plain lower-case DNS name, such as an IP address, and for a URL on a port other than 443,
    which the gate never passes on."""
    hosts = set()
    for name in names:
        url = urlsplit(name) if "://" in name else None
        host = url.hostname if url else name
        if url and url.port not in (None, 443):
            raise ValueError(f"the gate passes on only port 443: {name!r}")
        if not host or not HOST_PATTERN.fullmatch(host):
            raise ValueError(f"not a host name: {name!r}")
        hosts.add(host)
    return sorted(hosts)


class Gate:
    """The gate of one run: a proxy on `socket_path` that allows CONNECT to `hosts` on port 443 only. `upstream`
    is the operator's own proxy, an `http://` URL, or None to connect directly. `log` holds each request with the
    status the gate answered: 200, 403 or 502."""

    def __init__(self, socket_path, hosts, upstream=None):
        self.socket_path, self.hosts = str(socket_path), set(hosts)
        self.upstream = urlsplit(upstream) if upstream else None
        if self.upstream and (self.upstream.scheme != "http" or not self.upstream.hostname):
            raise ValueError("the operator's proxy must be an http:// URL, so its password is never sent in clear "
                             "to a TLS proxy")
        self.log, self._lock = [], threading.Lock()
        gate = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                gate._handle(self.rfile, self.connection)

        self.server = socketserver.ThreadingUnixStreamServer(self.socket_path, Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        os.unlink(self.socket_path)

    def _handle(self, rfile, client):
        request = rfile.readline(4096).decode("latin-1").strip()
        while rfile.readline(4096).strip():
            pass  # headers: none are passed on
        parts = request.split()
        target = parts[1] if len(parts) == 3 and parts[0] == "CONNECT" else None
        host, _, port = (target or "").lower().rpartition(":")
        ok = target is not None and port == "443" and host in self.hosts
        remote = None
        if ok:
            try:
                remote = self._open(host)
            except OSError:
                pass
        status = 403 if not ok else 502 if remote is None else 200
        with self._lock:
            self.log.append({"request": request[:200], "status": status})
        if remote is None:
            reason = {403: b"Forbidden", 502: b"Bad Gateway"}[status]
            client.sendall(b"HTTP/1.1 %d %s\r\nContent-Length: 0\r\n\r\n" % (status, reason))
            return
        client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        back = threading.Thread(target=_pipe, args=(remote, client), daemon=True)
        back.start()
        _pipe(client, remote)
        back.join()
        remote.close()

    def _open(self, host):
        if self.upstream is None:
            remote = socket.create_connection((host, 443), timeout=30)
            remote.settimeout(None)  # the timeout is for connecting; a model may take long to answer
            return remote
        remote = socket.create_connection((self.upstream.hostname, self.upstream.port or 80), timeout=30)
        auth = ""
        if self.upstream.username is not None:
            pair = f"{unquote(self.upstream.username)}:{unquote(self.upstream.password or '')}"
            auth = f"Proxy-Authorization: Basic {base64.b64encode(pair.encode()).decode()}\r\n"
        remote.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n{auth}\r\n".encode())
        reply = b""
        while b"\r\n\r\n" not in reply:
            chunk = remote.recv(4096)
            if not chunk:
                raise OSError("the upstream proxy closed the connection")
            reply += chunk
        if reply.split()[1:2] != [b"200"]:
            raise OSError("the upstream proxy refused the connection")
        remote.settimeout(None)
        return remote


def _pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
