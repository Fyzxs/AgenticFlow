"""Tests for engine/runner.py: service readiness, zero-step modes and the default step timeout.

The older Runner tests live in test_engine.py (RunnerTests).
Run: python -I engine/tests/run_all.py
"""

import json
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
import runner  # noqa: E402


def run(*args):
    proc = subprocess.run([PY, "-I", str(ENGINE / "runner.py"), *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class RunnerServiceAndStepTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fyzxsflow-runner-"))
        (self.root / ".fyzxsflow").mkdir()
        self.marker = self.root / "step-ran.txt"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def script(self, name: str, body: str) -> str:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return f'"{PY}" -I "{path}"'

    def config(self, mode: dict, services=None):
        cfg = {"modes": {"http": mode}, "services": services or {}}
        (self.root / ".fyzxsflow" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def marker_step(self):
        return {"name": "proofs", "run": self.script("mark.py", f"open({str(self.marker)!r}, 'w').write('x')\n")}

    def test_port_already_answering_before_start_fails_and_runs_nothing(self):
        port = free_port()
        stale = socket.socket()
        stale.bind(("127.0.0.1", port))
        stale.listen()
        try:
            started = self.root / "service-started.txt"
            start = self.script("svc.py", f"open({str(started)!r}, 'w').write('x')\nimport time; time.sleep(30)\n")
            self.config({"services": ["api"], "steps": [self.marker_step()]},
                        {"api": {"start": start, "port": port, "ready_timeout_s": 10}})
            code, out = run("http", "--root", str(self.root))
        finally:
            stale.close()
        self.assertEqual(code, 1, out)
        self.assertIn(f"port {port} already in use before service 'api' started", out)
        self.assertFalse(self.marker.exists())
        self.assertFalse(started.exists())  # the service was never started

    def test_service_that_exits_before_ready_fails_fast(self):
        port = free_port()
        start = self.script("svc.py", "raise SystemExit(5)\n")
        self.config({"services": ["api"], "steps": [self.marker_step()]},
                    {"api": {"start": start, "port": port, "ready_timeout_s": 60}})
        began = time.monotonic()
        code, out = run("http", "--root", str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("service 'api' exited with code 5 before it was ready", out)
        self.assertLess(time.monotonic() - began, 30)  # didn't sit out the 60s ready timeout
        self.assertFalse(self.marker.exists())

    def test_mode_with_no_steps_is_a_config_error(self):
        for mode in ({"steps": []}, {"note": "forgot the steps"}):
            self.config(mode)
            code, out = run("http", "--root", str(self.root))
            self.assertEqual(code, 2, out)
            self.assertIn("has no steps", out)
        self.config({"not_applicable": "no API in this repo"})
        self.assertEqual(run("http", "--root", str(self.root))[0], 0)

    def test_steps_get_a_default_timeout_and_zero_means_none(self):
        self.assertEqual(runner.DEFAULT_TIMEOUT_S, 3600)
        sleeper = self.script("sleep.py", "import time; time.sleep(2)\n")
        log = self.root / "step.log"
        saved = runner.DEFAULT_TIMEOUT_S
        runner.DEFAULT_TIMEOUT_S = 0.5
        try:
            timed_out = runner.run_step({"name": "slow", "run": sleeper}, "", self.root, log)
            self.assertEqual(timed_out["exit"], 124)  # no timeout_s: the default applied
            self.assertIn("timed out after 0.5s", log.read_text(encoding="utf-8"))
            unlimited = runner.run_step({"name": "slow", "run": sleeper, "timeout_s": 0}, "", self.root, log)
            self.assertEqual(unlimited["exit"], 0)  # 0 = no limit
        finally:
            runner.DEFAULT_TIMEOUT_S = saved


if __name__ == "__main__":
    unittest.main()
