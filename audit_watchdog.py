"""Run one Linux Codex process and reap its descendants at the phase deadline."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def run(deadline, command):
    # Linux reparents orphaned descendants to this process, including those
    # that detached into another session. Process-group timeouts miss those.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "could not register child subreaper")
    pid = os.getpid()
    children = Path(f"/proc/{pid}/task/{pid}/children")
    children.read_text()  # Check kernel support before starting Codex.
    logs = Path(os.environ.get("AUDIT_WATCHDOG_LOGS", "/logs/agent"))
    timed_out = False
    try:
        if time.monotonic() >= deadline:
            timed_out = True
        else:
            process = subprocess.Popen(command)
            try:
                status = process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        # As each direct child exits, any still-live grandchildren become
        # direct children here. Wait until Linux reports no children left.
        while True:
            for child in children.read_text().split():
                try:
                    os.kill(int(child), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                reaped, _ = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not reaped:
                time.sleep(0.01)
    if timed_out:
        (logs / "phase-cutoff.txt").write_text("deadline\n")
        status = 124
    (logs / "phase-closed.txt").write_text("reaped\n")
    return status


if __name__ == "__main__":
    sys.exit(run(float(sys.argv[1]), sys.argv[2:]))
