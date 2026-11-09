"""Tests for engine/egress.py and the Runner's "network" modes (airplane and connected).

Airplane is an intent: nothing here switches a network off. The tests check the proxy settings, the container
pull guard, the connection-table parsers and the monitor, and one real external connection attempt to a
reserved documentation address (192.0.2.1, TEST-NET-1: never a real host).
Run: python -I engine/tests/run_all.py
"""

import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ENGINE = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable
sys.path.insert(0, str(ENGINE))
import egress  # noqa: E402

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1180
  TCP    127.0.0.1:5000         127.0.0.1:61000        ESTABLISHED     4242
  TCP    10.0.0.5:61001         203.0.113.7:443        ESTABLISHED     4242
  TCP    10.0.0.5:61002         192.0.2.1:80           SYN_SENT        4243
  TCP    [::1]:5432             [::1]:61003            ESTABLISHED     4244
  TCP    [fe80::1%5]:61004      [2001:db8::1]:443      ESTABLISHED     4244
  UDP    0.0.0.0:5353           *:*                                    2000
"""

# /proc/net/tcp: local 127.0.0.1:5000 <- remote 127.0.0.1:61000 (inode 111); remote 203.0.113.7:443 (inode 222)
PROC_TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1388 0100007F:EE48 01 00000000:00000000 00:00000000 00000000  1000        0 111 1 0 20 4 30 10 -1
   1: 0500000A:EE49 077100CB:01BB 01 00000000:00000000 00:00000000 00000000  1000        0 222 1 0 20 4 30 10 -1
   2: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 333 1 0 20 4 30 10 -1
"""
# /proc/net/tcp6: remote ::1 port 5432 (inode 444)
PROC_TCP6 = """  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000000000000000000001000000:EE4B 00000000000000000000000001000000:1538 01 00000000:00000000 00:00000000 00000000  1000        0 444 1 0 20 4 30 10 -1
"""


class ParserTests(unittest.TestCase):
    def test_netstat_lines_become_connections_with_their_pid(self):
        conns = egress.parse_netstat(NETSTAT)
        self.assertIn((4242, "203.0.113.7", 443, "ESTABLISHED"), conns)
        self.assertIn((4244, "::1", 61003, "ESTABLISHED"), conns)
        self.assertNotIn(2000, [c[0] for c in conns])  # UDP has no remote end

    def test_proc_net_tcp_decodes_little_endian_addresses(self):
        v4 = egress.parse_proc_net_tcp(PROC_TCP)
        self.assertEqual(v4["111"], ("127.0.0.1", 61000, "ESTABLISHED"))
        self.assertEqual(v4["222"], ("203.0.113.7", 443, "ESTABLISHED"))
        self.assertEqual(v4["333"][2], "LISTEN")
        self.assertEqual(egress.parse_proc_net_tcp(PROC_TCP6)["444"], ("::1", 5432, "ESTABLISHED"))

    def test_only_non_local_live_connections_count(self):
        allow = egress.allowed_networks(["172.17.0.0/16", "cosmos.local"])
        self.assertFalse(egress.is_external("127.0.0.1", allow))
        self.assertFalse(egress.is_external("::1", allow))
        self.assertFalse(egress.is_external("::ffff:127.0.0.1", allow))
        self.assertFalse(egress.is_external("0.0.0.0", allow))
        self.assertFalse(egress.is_external("172.17.0.3", allow))
        self.assertTrue(egress.is_external("192.0.2.1", allow))
        self.assertTrue(egress.is_external("2001:db8::1", allow))
        found = egress.external(egress.parse_netstat(NETSTAT), allow)
        self.assertEqual(sorted((c[1], c[3]) for c in found),
                         [("192.0.2.1", "SYN_SENT"), ("2001:db8::1", "ESTABLISHED"), ("203.0.113.7", "ESTABLISHED")])

    def test_a_process_tree_includes_grandchildren_only(self):
        table = {1: (0, "init"), 10: (1, "cmd"), 11: (10, "dotnet"), 12: (11, "node"), 20: (1, "other")}
        self.assertEqual(egress.descendants([10], table), {10, 11, 12})

    def test_container_starts_must_not_pull(self):
        self.assertIsNotNone(egress.docker_pull_problem("docker compose -f e2e.yml up -d"))
        self.assertIsNotNone(egress.docker_pull_problem("docker run --rm redis:7"))
        self.assertIsNotNone(egress.docker_pull_problem("podman-compose up"))
        self.assertIsNone(egress.docker_pull_problem("docker compose -f e2e.yml up -d --pull never"))
        self.assertIsNone(egress.docker_pull_problem("docker run --pull=never --rm redis:7"))
        self.assertIsNone(egress.docker_pull_problem("docker compose down"))
        self.assertIsNone(egress.docker_pull_problem("npx playwright test"))

    def test_proxy_settings_point_at_a_closed_local_port_and_spare_loopback(self):
        env = egress.proxy_env(["cosmos.local"])
        self.assertEqual(env["HTTPS_PROXY"], egress.DEAD_PROXY)
        self.assertEqual(env["http_proxy"], egress.DEAD_PROXY)
        self.assertEqual(env["NO_PROXY"], "localhost,127.0.0.1,::1,cosmos.local")


class MonitorTests(unittest.TestCase):
    def test_monitor_records_each_external_connection_of_a_watched_tree_once(self):
        table = {100: (1, "cmd.exe"), 101: (100, "node.exe"), 200: (1, "browser.exe")}
        conns = [(101, "203.0.113.7", 443, "ESTABLISHED"), (101, "127.0.0.1", 5000, "ESTABLISHED"),
                 (200, "198.51.100.1", 443, "ESTABLISHED")]
        m = egress.Monitor(table=lambda: table, conns=lambda pids: [c for c in conns if c[0] in pids])
        m.watch(100, "step e2e")
        m.poll()
        m.poll()
        seen = m.stop()
        self.assertEqual(seen, [{"pid": 101, "process": "node.exe", "remote": "203.0.113.7:443",
                                 "state": "ESTABLISHED", "during": "step e2e"}])

    def test_a_broken_poll_is_recorded_not_swallowed(self):
        def boom():
            raise OSError("netstat missing")
        m = egress.Monitor(table=boom)
        m.watch(1, "step x")
        m.poll()
        self.assertEqual(m.errors, ["OSError: netstat missing"])

    def test_this_platforms_connection_table_sees_a_loopback_connection(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen()
        client = socket.create_connection(server.getsockname())
        try:
            conns = egress.connections({os.getpid()})
            ports = {c[2] for c in conns if c[1] == "127.0.0.1"}
            self.assertIn(server.getsockname()[1], ports, conns)
        finally:
            client.close()
            server.close()


class RunnerNetworkTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-egress-"))
        (self.root / ".fyzxsflow").mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def script(self, name: str, body: str) -> str:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return f'"{PY}" -I "{path}"'

    def run_mode(self, mode: dict):
        cfg = {"modes": {"e2e-airplane": mode}}
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        proc = subprocess.run([PY, "-I", str(ENGINE / "runner.py"), "e2e-airplane", "--root", str(self.root)],
                              capture_output=True, text=True)
        summaries = sorted((self.root / ".fyzxsflow" / "runs" / "_adhoc" / "runner").glob("*.json"))
        summary = json.loads(summaries[-1].read_text(encoding="utf-8")) if summaries else None
        return proc.returncode, proc.stdout + proc.stderr, summary

    def test_airplane_steps_get_the_dead_proxy_and_the_summary_says_airplane(self):
        out_file = self.root / "env.json"
        step = self.script("env.py", "import json, os\n"
                           f"json.dump({{k: os.environ.get(k) for k in ('HTTPS_PROXY', 'NO_PROXY')}}, "
                           f"open({str(out_file)!r}, 'w'))\n")
        code, out, summary = self.run_mode({"network": "airplane", "steps": [{"name": "e2e", "run": step}]})
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out_file.read_text(encoding="utf-8")),
                         {"HTTPS_PROXY": egress.DEAD_PROXY, "NO_PROXY": "localhost,127.0.0.1,::1"})
        self.assertEqual((summary["network"], summary["egress"]), ("airplane", []))

    def test_a_container_start_that_could_pull_is_refused_before_anything_runs(self):
        code, out, summary = self.run_mode({"network": "airplane",
                                            "steps": [{"name": "up", "run": "docker compose up -d"}]})
        self.assertEqual(code, 2, out)
        self.assertIn("--pull never", out)
        self.assertIsNone(summary)

    def test_an_unknown_network_value_is_a_configuration_error(self):
        code, out, _ = self.run_mode({"network": "offline", "steps": [{"name": "x", "run": "echo"}]})
        self.assertEqual(code, 2)
        self.assertIn('"connected" or "airplane"', out)

    def test_a_connected_mode_gets_no_proxy_and_is_recorded_as_connected(self):
        out_file = self.root / "env.txt"
        step = self.script("env.py", f"import os\nopen({str(out_file)!r}, 'w').write(str(os.environ.get('ALL_PROXY')))\n")
        cfg = {"modes": {"e2e-connected": {"network": "connected", "steps": [{"name": "e2e", "run": step}]}}}
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k.upper() != "ALL_PROXY"}
        proc = subprocess.run([PY, "-I", str(ENGINE / "runner.py"), "e2e-connected", "--root", str(self.root)],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(out_file.read_text(encoding="utf-8"), "None")
        summary = json.loads(sorted((self.root / ".fyzxsflow" / "runs" / "_adhoc" / "runner").glob("*.json"))[-1]
                             .read_text(encoding="utf-8"))
        self.assertEqual(summary["network"], "connected")
        self.assertNotIn("egress", summary)

    def test_a_connection_to_an_external_address_fails_an_airplane_mode(self):
        # Holds a connection attempt to TEST-NET-1 (reserved, never a real host) open for a few seconds, the way an
        # app calling out to a cloud service would, while the monitor polls.
        step = self.script("call_out.py", "import socket, sys, time\n"
                           "s = socket.socket()\ns.settimeout(4)\nt = time.monotonic()\n"
                           "try:\n    s.connect(('192.0.2.1', 80))\nexcept OSError as e:\n"
                           "    print('connect', type(e).__name__, round(time.monotonic() - t, 1))\n")
        code, out, summary = self.run_mode({"network": "airplane", "steps": [{"name": "e2e", "run": step}]})
        log = pathlib.Path(summary["steps"][0]["log"]).read_text(encoding="utf-8")
        if not summary["egress"] and "connect" in log and float(log.split()[-1]) < 1.0:
            self.skipTest(f"this machine refuses the attempt at once (no route), so it is never visible: {log!r}")
        self.assertEqual(code, 1, out)
        self.assertEqual(summary["result"], "fail")
        self.assertEqual([c["remote"] for c in summary["egress"]], ["192.0.2.1:80"])
        self.assertEqual(summary["egress"][0]["during"], "step e2e")
        self.assertIn("AIRPLANE VIOLATION", out)


if __name__ == "__main__":
    unittest.main()
