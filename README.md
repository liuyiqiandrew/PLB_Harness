# Physics audit harness

The [pilot handoff](handoff/READ-ME.txt) includes the PhysLiteBench patch, run plans, and results.

The pilot uses the first three task names in alphabetical order from the frozen roster
(entropy anomaly, finite-ion cloud and finite-layer phoresis). The other ten are held
out. Each development task gets five fresh Luna High attempts per condition. The
primary comparison is delayed written review versus standard Codex. Early written
review tests the effect of seeing the starter during derivation. The runner also
supports executable checks with either access condition.

Run these commands from `PLB_Harness/` with the audit-enabled benchmark checkout at `../PhysLiteBench/`.
Use `python3 run_audit_pilot.py` for the full written pilot. For one delayed written
audit on finite-ion cloud, use the benchmark runner.

```bash
python3 ../PhysLiteBench/scripts/run_science.py ../PhysLiteBench/tasks/finite-ion-cloud --audit delayed-written \
  --model gpt-5.6-luna --reasoning-effort high --restricted-network --trials 1
```

You can also prepare a batch, invoke the pinned Harbor 0.21.0 CLI directly,
and summarize its results. Use a fresh directory for each batch.

```bash
python3 run_audit_pilot.py --prepare ../PhysLiteBench/jobs/my-audit-pilot
harbor run -c ../PhysLiteBench/jobs/my-audit-pilot/job.json
python3 run_audit_pilot.py --summarize ../PhysLiteBench/jobs/my-audit-pilot
```

An audit uses four fresh Codex sessions in a single Harbor trial. The stages have
120 seconds for derivation, 75 for check design, 105 for review and 300 for repair.
The harness reserves five seconds per stage to stop Codex and its child processes.
Harbor waits for that cleanup before collecting files or starting verification.
The standard agent gets 600 seconds in one session. Delayed runs first receive the
starter at review. Only the repair verifier receives the hidden tests. For executable
reviews, the harness runs the agent's checks against the starter and gives the
output to the repair session. The review-stage copy of the checks is used for
post-episode replay against both completed controls.

If an audit stage misses its file deadline, the harness passes its public messages
to the next stage and records the missing file. A pass requires the final repair
to finish and receive hidden reward 1. The pilot summary reports intermediate
timeouts and missing handoffs alongside pass rates.
