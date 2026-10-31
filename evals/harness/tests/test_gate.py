"""The network gate: the jail has no network, and the gate passes on only CONNECT to the allowed hosts."""

import base64
import socket
import socketserver
import subprocess
import threading
import types
import unittest

from helpers import TempCase

import contain
import gate
import manifest

JAIL = contain.available()


class Upstream:
    """A fake operator proxy on loopback: records each request, answers 200 and then echoes what it receives."""

    def __init__(self):
        self.requests = []
        upstream = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                head = b""
                while not head.endswith(b"\r\n\r\n"):
                    head += self.rfile.read(1)
                upstream.requests.append(head.decode())
                self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                for line in iter(lambda: self.rfile.readline(), b""):
                    self.wfile.write(line)

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://user:p%40ss@127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def ask(path, request):
    """Send one request to the gate's socket and return the first reply line and the open connection."""
    client = socket.socket(socket.AF_UNIX)
    client.connect(str(path))
    client.sendall(request.encode())
    reply = client.makefile("rb").readline().decode().strip()
    return reply, client


class Gate(TempCase):
    def setUp(self):
        super().setUp()
        self.upstream = Upstream()
        self.addCleanup(self.upstream.close)

    def test_only_connect_to_an_allowed_host_on_443_is_passed_on(self):
        with gate.Gate(self.tmp / "gate.sock", ["api.example.com"], self.upstream.url) as found:
            for request in ("CONNECT other.example.com:443 HTTP/1.1\r\n\r\n",
                            "CONNECT api.example.com:80 HTTP/1.1\r\n\r\n",
                            "GET http://api.example.com/ HTTP/1.1\r\nHost: api.example.com\r\n\r\n"):
                with self.subTest(request=request):
                    reply, client = ask(self.tmp / "gate.sock", request)
                    client.close()
                    self.assertIn(" 403 ", reply)
            request = "CONNECT API.example.com:443 HTTP/1.1\r\nX-Secret: 1\r\n\r\n"
            reply, client = ask(self.tmp / "gate.sock", request)
            self.addCleanup(client.close)
            self.assertIn(" 200 ", reply)
            client.sendall(b"hello\n")
            self.assertEqual(client.makefile("rb").readline(), b"hello\n")
        self.assertEqual([entry["status"] for entry in found.log], [403, 403, 403, 200])
        self.assertEqual(len(self.upstream.requests), 1)
        sent = self.upstream.requests[0]
        self.assertTrue(sent.startswith("CONNECT api.example.com:443 HTTP/1.1\r\n"))
        self.assertIn(f"Proxy-Authorization: Basic {base64.b64encode(b'user:p@ss').decode()}", sent)
        self.assertNotIn("X-Secret", sent)
        self.assertFalse((self.tmp / "gate.sock").exists())

    def test_the_allow_list_takes_only_plain_host_names(self):
        self.assertEqual(gate.allowed_hosts(["api.example.com", "https://models.example.com:443/v1"]),
                         ["api.example.com", "models.example.com"])
        for bad in ("localhost", "10.0.0.1:443", "10.0.0.1", "https://169.254.169.254/v1", "API.example.com",
                    "*.example.com", "https://", "https://models.example.com:8443/v1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gate.allowed_hosts([bad])


    def test_a_host_that_cannot_be_reached_is_answered_502_and_logged(self):
        with gate.Gate(self.tmp / "gate.sock", ["api.example.com"], "http://127.0.0.1:9") as found:
            reply, client = ask(self.tmp / "gate.sock", "CONNECT api.example.com:443 HTTP/1.1\r\n\r\n")
            client.close()
        self.assertIn(" 502 ", reply)
        self.assertEqual(found.log[0]["status"], 502)

    def test_a_direct_tunnel_has_no_timeout(self):
        ends = socket.socketpair()
        self.addCleanup(lambda: [end.close() for end in ends])
        ends[0].settimeout(30)
        connect = socket.create_connection
        socket.create_connection = lambda address, timeout=None: ends[0]
        self.addCleanup(setattr, socket, "create_connection", connect)
        with gate.Gate(self.tmp / "gate.sock", ["api.example.com"]) as found:
            self.assertIsNone(found._open("api.example.com").gettimeout())

    def test_the_operator_proxy_must_be_plain_http(self):
        for url in ("https://user:secret@proxy.example:443", "socks5://proxy.example:1080"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "http:// URL"):
                gate.Gate(self.tmp / "gate.sock", [], url)


class Run(TempCase):
    def run_of(self, **extra):
        world = self.tmp / "world"
        world.mkdir(exist_ok=True)
        host = types.SimpleNamespace(ENV_KEYS=("HOST_BASE_URL",), CREDENTIAL_FILES=(), environment=lambda env: env,
                                     **extra)
        env = {"PATH": "/usr/bin:/bin", "HTTPS_PROXY": "http://operator-proxy.example:8080",
               "NO_PROXY": "localhost", "HOST_BASE_URL": "https://models.example.com/v1"}
        return contain.Containment(host, "task", world, manifest.manifest(world), root=self.tmp / "run",
                                   operator_env=env, operator_home=self.tmp / "operator")

    def test_the_gate_is_the_only_proxy_and_the_model_hosts_are_its_allow_list(self):
        run = self.run_of(MODEL_HOSTS=("api.example.com",))
        self.assertEqual(run.hosts, ["api.example.com", "models.example.com"])
        self.assertEqual(run.upstream, "http://operator-proxy.example:8080")
        self.assertEqual({key: run.env[key] for key in contain.PROXY_KEYS},
                         dict.fromkeys(contain.PROXY_KEYS, gate.ADDRESS))
        self.assertNotIn("NO_PROXY", run.env)
        self.assertNotIn("operator-proxy", " ".join(run.env.values()))
        with self.assertRaisesRegex(contain.ContainmentError, "allow list"):
            self.run_of(MODEL_HOSTS=("localhost",))

    @unittest.skipIf(JAIL, f"no containment on this machine: {JAIL}")
    def test_the_jail_reaches_nothing_but_the_gate(self):
        listener = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        run = self.run_of()
        run.upstream = None
        probe = ("import socket, sys\n"
                 "try:\n"
                 f"    socket.create_connection(('127.0.0.1', {port}), timeout=5)\n"
                 "    print('direct: open')\n"
                 "except OSError:\n"
                 "    print('direct: refused')\n"
                 f"c = socket.create_connection(('127.0.0.1', {gate.PORT}))\n"
                 "c.sendall(b'CONNECT other.example.com:443 HTTP/1.1\\r\\n\\r\\n')\n"
                 "print('gate:', c.makefile('rb').readline().decode().strip())\n")
        with run.gate() as found:
            result = subprocess.run(run.jail([contain.PYTHON, "-I", "-c", probe]), capture_output=True, text=True,
                                    env=run.env, timeout=60)
        self.assertEqual(result.stdout, "direct: refused\ngate: HTTP/1.1 403 Forbidden\n", result.stderr)
        self.assertEqual(found.log, [{"request": "CONNECT other.example.com:443 HTTP/1.1", "status": 403}])


if __name__ == "__main__":
    unittest.main()
