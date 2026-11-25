"""Linux container smoke test for Codex stage deadlines. Requires an isolated /logs/agent."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


HERE = Path(__file__).resolve()
WATCHDOG = HERE.with_name("audit_watchdog.py")
CUTOFF = Path("/logs/agent/phase-cutoff.txt")
CLOSED = CUTOFF.with_name("phase-closed.txt")


def fake_cli(mode, work):
    # A detached child forks again. Its parent exits, leaving the writer orphaned.
    child = os.fork()
    if child == 0:
        os.setsid()
        if os.fork():
            os._exit(0)
        (work / "writer.pid").write_text(str(os.getpid()))
        for _ in range(500):
            if (work / "verifier-uploaded").exists():
                (work / "late-write").touch()
                os._exit(0)
            time.sleep(.01)
        os._exit(0)
    os.waitpid(child, 0)
    while not (work / "writer.pid").exists():
        time.sleep(.01)
    if mode == "timeout":
        time.sleep(5)
    return 0


@unittest.skipUnless(sys.platform == "linux" and Path("/.dockerenv").is_file(),
                     "requires a disposable Linux Docker container")
class AuditWatchdogTest(unittest.TestCase):
    def setUp(self):
        CUTOFF.parent.mkdir(parents=True, exist_ok=True)
        self.assertFalse(CUTOFF.exists(), "use a fresh test container")
        self.addCleanup(CUTOFF.unlink, missing_ok=True)
        self.addCleanup(CLOSED.unlink, missing_ok=True)

    def test_unguarded_writer_runs_after_cli_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            subprocess.run([sys.executable, str(HERE), "--fake-cli", "normal", str(work)],
                           timeout=5, check=True)
            (work / "verifier-uploaded").touch()
            for _ in range(100):
                if (work / "late-write").exists():
                    break
                time.sleep(.01)
            self.assertTrue((work / "late-write").exists())

    def test_normal_exit_and_timeout(self):
        with subprocess.Popen(["sleep", "20"]) as sibling:
            try:
                for mode in ("normal", "timeout"):
                    with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                        work = Path(tmp)
                        limit = time.monotonic() + (1 if mode == "timeout" else 5)
                        command = [sys.executable, str(WATCHDOG), str(limit),
                                   sys.executable, str(HERE), "--fake-cli", mode, str(work)]
                        result = subprocess.run(command, timeout=8)
                        self.assertEqual(result.returncode, 124 if mode == "timeout" else 0)
                        self.assertEqual(CUTOFF.exists(), mode == "timeout")
                        pid = (work / "writer.pid").read_text()
                        self.assertFalse(Path(f"/proc/{pid}").exists(), "detached writer survived")
                        self.assertTrue(CLOSED.exists(), "missing cleanup acknowledgement")
                        CLOSED.unlink()
                        (work / "verifier-uploaded").touch()
                        time.sleep(.1)
                        self.assertFalse((work / "late-write").exists())
                        self.assertIsNone(sibling.poll(), "unrelated process was stopped")
            finally:
                sibling.terminate()


if __name__ == "__main__":
    if sys.argv[1:2] == ["--fake-cli"]:
        sys.exit(fake_cli(sys.argv[2], Path(sys.argv[3])))
    unittest.main()
