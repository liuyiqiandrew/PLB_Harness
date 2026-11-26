# Run the harness on PhysLiteBench

Start Docker, sign in to Codex, and have either uv or Harbor 0.21.0 installed. Run the commands below from the directory containing `PLB_Harness/`.

**Set up a fresh benchmark checkout.** Skip this step if your sibling `PhysLiteBench/` checkout already has the audit patch.

```bash
git clone --branch luna-high-qualified-tasks https://github.com/liuyiqiandrew/PhysLiteBench.git PhysLiteBench
git -C PhysLiteBench switch --detach 1e9c32e264744e455b652464cb5bc3e162e8989e
git -C PhysLiteBench apply ../PLB_Harness/handoff/physlitebench-audit.patch
```

**Run one audit.** Replace `finite-ion-cloud` to try another benchmark task.

```bash
python3 PhysLiteBench/scripts/run_science.py PhysLiteBench/tasks/finite-ion-cloud --audit delayed-written --trials 1
```

**Run the 45-trial written pilot.**

```bash
python3 PLB_Harness/run_audit_pilot.py
```

The pilot writes grades to `PhysLiteBench/jobs/audit-pilot-<timestamp>/summary.json`. The [saved pilot report](results/report.md) contains the grades from the original run.
