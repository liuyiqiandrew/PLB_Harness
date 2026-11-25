"""Prepare, run and summarize the three-task no-hint Luna High development pilot."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess

from benchmark import ROOT, harbor_command, restrict_network
from physics_audit import CONDITIONS, prepare_audit
from score_audit_checks import score_trial

TASKS = ("entropy-anomaly", "finite-ion-cloud", "finite-layer-phoresis")
ARMS = ("baseline", *CONDITIONS)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def prepare(directory, tasks, conditions, trials, concurrency):
    roster = json.loads((ROOT / "results/task-roster.json").read_text())["tasks"]
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError(f"choose a new or empty batch directory: {directory}")
    cells = []
    for task in tasks:
        source = ROOT / "tasks" / task
        for name, digest in roster[task]["source_sha256"].items():
            if sha256((source / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"task file differs from frozen roster: {task}/{name}")
        for condition in conditions:
            cell = directory / "tasks" / f"{task}--{condition}"
            shutil.copytree(source, cell, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git"))
            restrict_network(cell)
            if condition != "baseline":
                prepare_audit(cell, condition)
            cells.append({"path": str(cell)})
    auth = os.environ.get("CODEX_AUTH_JSON_PATH", str(Path.home() / ".codex/auth.json"))
    config = {"job_name": "runs", "jobs_dir": str(directory), "n_attempts": trials,
              "n_concurrent_trials": concurrency, "agent_setup_timeout_multiplier": 3,
              "agents": [{"name": "codex", "model_name": "gpt-5.6-luna",
                          "kwargs": {"version": "0.154.0", "reasoning_effort": "high", "web_search": "disabled"},
                          "env": {"CODEX_AUTH_JSON_PATH": auth}}],
              "environment": {"type": "docker"}, "tasks": cells}
    write_json(directory / "job.json", config)
    write_json(directory / "plan.json", {"tasks": tasks, "conditions": conditions, "trials_per_cell": trials,
                                         "held_out": sorted(set(roster) - set(TASKS)),
                                         "model": "gpt-5.6-luna", "reasoning_effort": "high", "hint": "none"})


def elapsed(timing):
    if timing and timing.get("started_at") and timing.get("finished_at"):
        start, finish = (datetime.fromisoformat(timing[k].replace("Z", "+00:00"))
                         for k in ("started_at", "finished_at"))
        return (finish - start).total_seconds()


def read_trial(path, condition):
    result = json.loads(path.read_text())
    phases = (result.get("step_results") or []) if condition != "baseline" else [result]
    task = Path(result.get("config", {}).get("task", {}).get("path") or ".")
    guarded = (task / "steps/derive/workdir/.audit-runtime/audit_watchdog.py").is_file()
    errors = set()
    if result.get("exception_info"):
        errors.add(result["exception_info"]["exception_type"])
    steps = []
    missing = False
    reward = None
    for phase in phases:
        name = phase.get("step_name", "baseline")
        rewards = (phase.get("verifier_result") or {}).get("rewards") or {}
        agent = phase.get("agent_result") or {}
        raw_error = (phase.get("exception_info") or {}).get("exception_type")
        error = raw_error
        closed = None
        if guarded:
            logs = path.parent / "steps" / name / "agent"
            closed = (logs / "phase-closed.txt").is_file() and (logs / "phase-closed.txt").read_text() == "reaped\n"
            cutoff = logs / "phase-cutoff.txt"
            if not closed:
                errors.add("MissingPhaseCleanup")
            if cutoff.is_file() and cutoff.read_text() == "deadline\n" and raw_error in (
                None, "NonZeroAgentExitCodeError", "AgentTimeoutError"
            ):
                error = "AgentTimeoutError"
        if error:
            errors.add(error)
        steps.append({"name": name, "seconds": elapsed(phase.get("agent_execution")),
                      "exception": error, "harbor_exception": raw_error, "closed": closed,
                      "handoff": rewards.get("audit_artifact"),
                      **{k: agent.get(k) for k in ("n_input_tokens", "n_cache_tokens", "n_output_tokens", "cost_usd")}})
        if name in ("repair", "baseline"):
            reward = rewards.get("reward")
        elif rewards.get("audit_artifact") == 0:
            missing = True
    if any(e != "AgentTimeoutError" for e in errors):
        status = "error"
    elif steps and steps[-1]["name"] in ("repair", "baseline") and steps[-1]["exception"] == "AgentTimeoutError":
        status = "timeout"
    elif reward in (0, 1) and steps and phases[-1].get("agent_execution"):
        status = "pass" if reward == 1 else "fail"
    elif "AgentTimeoutError" in errors:
        status = "timeout"
    elif missing:
        status = "missing_artifact"
    else:
        status = "error"
        errors.add("MissingAgentOrVerifierResult")
    totals = {}
    for key in ("seconds", "n_input_tokens", "n_cache_tokens", "n_output_tokens", "cost_usd"):
        values = [s[key] for s in steps]
        totals[key] = sum(values) if values and None not in values else None
    return {"trial": path.parent.name, "status": status, "reward": reward, "errors": sorted(errors),
            "wall_seconds": elapsed(result), "steps": steps, "totals": totals}


def summarize(directory, replay_image=None):
    plan = json.loads((directory / "plan.json").read_text())
    repeats = plan["trials_per_cell"]
    cells = {f"{t}--{c}": [] for t in plan["tasks"] for c in plan["conditions"]}
    for path in sorted((directory / "runs").glob("*/result.json")):
        result = json.loads(path.read_text())
        cell = Path(result["config"]["task"]["path"]).name
        task, condition = cell.split("--")
        trial = read_trial(path, condition)
        if condition.endswith("executable"):
            trial["check_quality"] = score_trial(path.parent, directory / "tasks" / cell, task, replay_image)
        cells[cell].append(trial)
    panels = {}
    for condition in plan["conditions"]:
        groups = [cells[f"{task}--{condition}"] for task in plan["tasks"]]
        statuses = [t["status"] for group in groups for t in group]
        complete = all(len(group) == repeats for group in groups) and "error" not in statuses
        passed = statuses.count("pass")
        audit_steps = [step for group in groups for trial in group for step in trial["steps"]
                       if step["name"] not in ("repair", "baseline")]
        panels[condition] = {"planned": repeats * len(groups), "recorded": len(statuses), "passes": passed,
                             "hidden_passes": sum(t["reward"] == 1 for g in groups for t in g),
                             "exception_free_passes": sum(t["status"] == "pass" and not t["errors"]
                                                          for g in groups for t in g),
                             "audit_step_timeouts": sum(s["exception"] == "AgentTimeoutError" for s in audit_steps),
                             "incomplete_handoffs": sum(s["handoff"] == 0 for s in audit_steps),
                             "timeouts": statuses.count("timeout"), "missing_artifacts": statuses.count("missing_artifact"),
                             "errors": statuses.count("error"), "pass_rate": passed / len(statuses) if complete else None}
    base = panels.get("baseline", {}).get("pass_rate")
    for condition, panel in panels.items():
        if condition != "baseline" and base is not None and panel["pass_rate"] is not None:
            panel["delta_percentage_points"] = round(100 * (panel["pass_rate"] - base), 3)
    write_json(directory / "summary.json", {**plan, "panels": panels, "cells": cells})
    print(json.dumps(panels, indent=2))
    return all(p["pass_rate"] is not None for p in panels.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", type=Path, metavar="DIR", help="Stage inputs and job.json, then exit")
    mode.add_argument("--summarize", type=Path, metavar="DIR", help="Score results from the prepared batch")
    parser.add_argument("--tasks", choices=TASKS, nargs="+", default=TASKS)
    parser.add_argument("--conditions", choices=ARMS, nargs="+", default=ARMS[:3])
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--replay-image", help="Image with task dependencies for replaying executable checks")
    args = parser.parse_args()
    if args.summarize:
        return 0 if summarize(args.summarize.resolve(), args.replay_image) else 1
    if min(args.trials, args.concurrency) < 1:
        parser.error("trials and concurrency must be positive")
    if len(set(args.tasks)) != len(args.tasks) or len(set(args.conditions)) != len(args.conditions):
        parser.error("task and condition names must be unique")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = (args.prepare or ROOT / "jobs" / f"audit-pilot-{stamp}").resolve()
    prepare(directory, args.tasks, args.conditions, args.trials, args.concurrency)
    print(directory / "job.json", flush=True)
    if args.prepare:
        return 0
    result = subprocess.run([*harbor_command(), "run", "-c", str(directory / "job.json")], cwd=ROOT)
    complete = summarize(directory, args.replay_image)
    return result.returncode or int(not complete)


if __name__ == "__main__":
    raise SystemExit(main())
