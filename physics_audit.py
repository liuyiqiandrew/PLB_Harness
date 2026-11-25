"""Prepare a staged PhysLiteBench copy as a four-step Harbor task."""
from pathlib import Path
import shutil


CONDITIONS = ("early-written", "delayed-written", "early-executable", "delayed-executable")
RUNTIME = "/app/.audit-runtime"

# Harbor calls Codex through a noninteractive Bash shell, which reads BASH_ENV.
# The real Codex process gets an empty BASH_ENV, including for its tool shells.
CODEX_SHELL = """\
codex() {
    if [ "${1:-}" != exec ]; then
        command codex "$@"
        return $?
    fi
    BASH_ENV= flock --close /app/.audit-runtime/lock bash -c '
        set -eu
        read -r deadline < /app/.audit-runtime/deadline
        exec python /app/.audit-runtime/audit_watchdog.py "$deadline" "$@"
    ' _ "$(type -P codex)" "$@"
}
"""

# Recover only messages Codex displayed to the user in the current step.
RECOVER_NOTE = """\
import json
from pathlib import Path
import sys

note = Path(sys.argv[1])
log = Path("/logs/agent/codex.txt")
messages = []
if log.exists():
    for line in log.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            messages.append(item["text"])
text = ("Recovered from public stage messages.\\n\\n" + "\\n\\n".join(messages)
        if messages else "Missing stage note. No public agent message was recorded.")
note.write_text(text + "\\n")
(Path("/logs/verifier") / note.name).write_text(text + "\\n")
"""

# Run after Harbor archives the review, before the repair agent sees its inputs.
RUN_CHECKS = """\
cp /tests/starter.py /app/model.py
cd /app
python - <<'PYTEST'
import json
import os
from pathlib import Path
import subprocess
import sys
import time

test = Path("audit/test_physics.py")
if test.is_file() and test.stat().st_size:
    check_logs = Path("/logs/verifier/check-process")
    check_logs.mkdir(exist_ok=True)
    result = subprocess.run(
        [sys.executable, "/app/.audit-runtime/audit_watchdog.py", str(time.monotonic() + 45),
         sys.executable, "-m", "pytest", "-q", str(test)],
        env={**os.environ, "AUDIT_WATCHDOG_LOGS": str(check_logs), "BASH_ENV": ""},
        capture_output=True, text=True,
    )
    if not (check_logs / "phase-closed.txt").exists():
        raise RuntimeError("Generated test process did not confirm cleanup")
    data = {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
else:
    data = {"status": "not_run", "exit_code": None, "reason": "No generated test was saved."}
record = json.dumps(data, indent=2) + "\\n"
Path("/app/audit/test-result.json").write_text(record)
Path("/logs/verifier/test-result.json").write_text(record)
PYTEST
"""


def prepare_audit(task: Path, condition: str) -> None:
    """Modify only the job's task copy, before Harbor builds its public image."""
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown audit condition {condition!r}")
    delayed = condition.startswith("delayed-")
    executable = condition.endswith("-executable")
    original_instruction = (task / "instruction.md").read_text().strip()
    starter = task / "environment/model.py"
    access = ("The starter will be supplied at review." if delayed else
              "You may inspect the starter code.")
    review = (
        "Read the derivation and checks. First save one of your proposed physical checks "
        "as a runnable pytest function in audit/test_physics.py, using the documented Model API. "
        "Put any numerical calculation needed for that check in the test itself. The harness "
        "will run it on the starter. Then compare /app/model.py with the derivation, write "
        "your findings in audit/review.md and add further checks if time permits."
        if executable else
        "Read the derivation, checks and /app/model.py. Write your first finding to "
        "audit/review.md before expanding it. Identify concrete discrepancies and uncertainties. "
        "Evaluate the checks in writing without running them."
    )
    steps = [
        ("derive", 120, ("derivation.md",),
         f"{access} Read the apparatus description and inspect the calibration schema. "
         "Write your first governing equation and its assumptions to audit/derivation.md "
         "as soon as you have them. Append a short derivation of the observable and any "
         "unresolved terms. Leave numerical fitting and implementation for repair."),
        ("design", 75, ("checks.md",),
         f"{access} Read audit/derivation.md. Immediately record one physical check in "
         "audit/checks.md with inputs, expected result and justified tolerance. "
         "Add a second independent check if time permits."),
        ("review", 105, ("review.md", "test_physics.py") if executable else ("review.md",),
         review),
        ("repair", 300, (),
         "Read audit/derivation.md, audit/checks.md and audit/review.md. "
         + ("Inspect audit/test-result.json for the generated test results. " if executable else "")
         + "Use this evidence to repair /app/model.py. Check it against the public tests."),
    ]

    config = task / "task.toml"
    toml = 'multi_step_reward_strategy = "final"\n' + config.read_text()
    toml += f'\n[environment.env]\nBASH_ENV = "{RUNTIME}/shell.sh"\n'
    toml += (f'\n[[verifier.collect]]\ncommand = "flock {RUNTIME}/lock '
             f'rm -f {RUNTIME}/deadline"\n')
    for name, seconds, outputs, prompt in steps:
        step = task / "steps" / name
        step.mkdir(parents=True)
        if name == "repair":
            prompt += f"\n\n{original_instruction}"
        else:
            prompt = ("Use /app/task.md, /app/README.md and /app/data. Leave public "
                      "inputs unchanged and save your work under /app/audit. " + prompt)
        (step / "instruction.md").write_text(
            f"{prompt}\nYou have {seconds} seconds for this step.\n"
        )
        toml += f'\n[[steps]]\nname = "{name}"\n'
        if outputs:
            tests = step / "tests"
            tests.mkdir()
            checks = " && ".join(f"test -s /app/audit/{output}" for output in outputs)
            script = (
                "#!/bin/bash\nset -eu\nmkdir -p /logs/verifier\n"
                f"if {checks}; then\n    reward=1\nelse\n    reward=0\nfi\n"
                f"if [ ! -s /app/audit/{outputs[0]} ]; then\n"
                f"    python - /app/audit/{outputs[0]} <<'NOTE'\n{RECOVER_NOTE}NOTE\nfi\n"
            )
            if name == "review" and executable:
                shutil.copyfile(starter, tests / "starter.py")
                script += RUN_CHECKS
            script += 'printf \'{"audit_artifact": %s}\\n\' "$reward" > /logs/verifier/reward.json\n'
            (tests / "test.sh").write_text(script)
        else:
            # Shared tests would be uploaded after every step. Only the final
            # step may receive the original private verifier.
            (task / "tests").rename(step / "tests")
        toml += f"[steps.agent]\ntimeout_sec = {seconds}\n"
        workdir = step / "workdir"
        workdir.mkdir()
        setup = "#!/bin/bash\nset -eu\n"
        if name == "derive":
            (workdir / "task.md").write_text(original_instruction + "\n")
            runtime = workdir / ".audit-runtime"
            runtime.mkdir()
            (runtime / "shell.sh").write_text(CODEX_SHELL)
            shutil.copyfile(Path(__file__).with_name("audit_watchdog.py"), runtime / "audit_watchdog.py")
            setup += "mkdir -p /app/audit\n"
            if delayed:
                setup += "test ! -s /app/model.py\nrm -f /app/model.py\n"
        elif name in ("review", "repair"):
            shutil.copyfile(starter, workdir / "model.py")
        # Start the in-container timer before Harbor starts its own. Leave time
        # for process cleanup and Harbor's normal Codex session-log archival.
        setup += (f"python -c 'import time; print(time.monotonic() + {seconds - 5})'"
                  f" > {RUNTIME}/deadline\nrm /app/setup.sh\n")
        (workdir / "setup.sh").write_text(setup)
    if delayed:
        # Keep the existing Dockerfile and omit the implementation from every image layer.
        starter.write_bytes(b"")
    config.write_text(toml)
