"""Replay generated pytest checks on two completed models after a Harbor job."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from benchmark import ROOT, shortcut_model

# Run inside the isolated container. Only assertion failures in the test body
# count as evidence that a check rejects a model.
PYTEST_DRIVER = """
import json, pytest

class Results:
    def __init__(self):
        self.cases = {}
        self.errors = []
    def pytest_runtest_makereport(self, item, call):
        if call.when == 'call':
            outcome = 'pass'
            if call.excinfo:
                outcome = 'assertion' if call.excinfo.errisinstance(AssertionError) else 'error'
            self.cases[item.nodeid] = outcome
    def pytest_runtest_logreport(self, report):
        if report.skipped or hasattr(report, 'wasxfail') or (report.when != 'call' and report.failed):
            self.errors.append(report.nodeid)

results = Results()
code = pytest.main(['-q', '--tb=no', '-p', 'no:cacheprovider', 'audit/test_physics.py'], plugins=[results])
print('AUDIT_RESULT ' + json.dumps({'exit': int(code), 'cases': results.cases, 'errors': results.errors}))
"""


def replay(image, directory):
    command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--user", "65534:65534", "--memory", "1g",
               "--cpus", "1", "--pids-limit", "128", "--tmpfs", "/tmp:rw,size=64m",
               "-v", f"{directory}:/app:ro", "-w", "/app", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "--entrypoint", "timeout", image, "-k", "2", "60", "python", "/app/.audit-replay.py"]
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode:
        return {"status": "timeout" if proc.returncode in (124, 137) else "execution_error",
                "returncode": proc.returncode, "detail": proc.stderr[-2000:]}
    lines = [s for s in proc.stdout.splitlines() if s.startswith("AUDIT_RESULT ")]
    if len(lines) != 1:
        return {"status": "invalid"}
    data = json.loads(lines[0].removeprefix("AUDIT_RESULT "))
    outcomes = set(data["cases"].values())
    status = "invalid"
    if data["exit"] == 5 and not outcomes:
        status = "no_tests"
    elif not data["errors"] and outcomes:
        if data["exit"] == 0 and outcomes == {"pass"}:
            status = "accept"
        elif data["exit"] == 1 and "assertion" in outcomes and outcomes <= {"pass", "assertion"}:
            status = "reject"
    return {"status": status, **data}


def score_trial(trial, source, task, image=None):
    test = trial / "steps/review/artifacts/app/audit/test_physics.py"
    if not test.is_file() or test.is_symlink() or not test.resolve().is_relative_to(trial.resolve()):
        return {"status": "missing"}
    if not image:
        build = subprocess.run(["docker", "build", "-q", str(source / "environment")],
                               capture_output=True, text=True)
        if build.returncode:
            return {"status": "image_build_error", "detail": build.stderr[-2000:]}
        image = build.stdout.strip().splitlines()[-1]
    controls = {"oracle": source / "solution/model.py",
                "shortcut": shortcut_model(ROOT / "scripts", task)}
    row = {"status": "invalid"}
    with tempfile.TemporaryDirectory(prefix="replay-check-") as tmp:
        app = Path(tmp) / "app"
        shutil.copytree(source / "environment", app)
        (app / "audit").mkdir()
        shutil.copyfile(test, app / "audit/test_physics.py")
        (app / ".audit-replay.py").write_text(PYTEST_DRIVER)
        for control, model in controls.items():
            shutil.copyfile(model, app / "model.py")
            row[control] = replay(image, app)
    correct, shortcut = row["oracle"], row["shortcut"]
    if correct["status"] == shortcut["status"] == "no_tests":
        row["status"] = "no_tests"
    elif {correct["status"], shortcut["status"]} <= {"accept", "reject"}:
        if set(correct["cases"]) == set(shortcut["cases"]):
            row["status"] = ("useful" if correct["status"] == "accept" and shortcut["status"] == "reject"
                             else "not_discriminating")
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path, help="Single-task run_science job with frozen-task and run-timing.json")
    parser.add_argument("--image", help="Use an existing image with the task's Python dependencies")
    args = parser.parse_args()
    job = args.job.resolve()
    task = json.loads((job / "run-timing.json").read_text())["task"]
    rows = [{"trial": p.parent.name, **score_trial(p.parent, job / "frozen-task", task, args.image)}
            for p in sorted(job.glob("*/result.json"))]
    (job / "check-quality.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))
