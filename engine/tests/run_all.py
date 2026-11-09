"""Run every engine test: python -I engine/tests/run_all.py"""

import pathlib
import subprocess
import sys
import unittest

here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here))

suite = unittest.defaultTestLoader.discover(str(here), pattern="test_[egpimcrfs]*.py")
result = unittest.TextTestRunner(verbosity=1).run(suite)

hook = subprocess.run([sys.executable, "-I", str(here / "test_block_kill_by_name.py")], capture_output=True, text=True)
print(hook.stdout.strip() or hook.stderr.strip())

sys.exit(0 if result.wasSuccessful() and hook.returncode == 0 else 1)
