# No-hint physics audit pilot

Delayed written review tied standard Codex on hidden grading and produced one fewer on-time pass. Early written review produced no passes. These three development tasks provide no evidence of an overall improvement from the harness at Luna High.

| No-hint condition | Hidden passes | On-time passes | Median agent time | Recorded API-equivalent cost for 15 attempts |
|---|---:|---:|---:|---:|
| Standard Codex | 4/15 | 4/15 | 214 s | $0.354 |
| Early written review | 0/15 | 0/15 | 361 s | $0.624 |
| Delayed written review | 4/15 | 3/15 | 414 s | $0.623 |

A hidden pass means the final submitted predictor received reward 1. An on-time pass also requires the final coding stage to finish before its deadline. The benchmark grades the saved predictor even when that stage times out. Intermediate audit deadlines are recorded separately. All three on-time delayed passes hit at least one intermediate deadline. Recorded costs are Harbor estimates for subscription-authenticated runs. Interrupted requests can have incomplete usage records.

| Development task | Standard hidden passes | Early hidden passes | Delayed hidden passes |
|---|---:|---:|---:|
| Entropy anomaly | 0/5 | 0/5 | 0/5 |
| Finite-ion cloud | 3/5 | 0/5 | 2/5 |
| Finite-layer phoresis | 1/5 | 0/5 | 2/5 |

The observed on-time difference for delayed review versus standard Codex was **−6.7 percentage points**. Its 95% credible interval was **−30.1 to +19.7 points** for this fixed, equally weighted task mix. The interval uses independent Jeffreys beta priors for the six task/condition rates and 200,000 posterior draws with seed 20261120. Five trials per cell leave substantial uncertainty.

## What happened during review

A successful delayed phoresis audit traced the error to how the starter weighted interaction forces under slip. Its repair changed that weighting and passed. In an early audit of the same task, the agent held the force integral fixed and predicted a slip/no-slip velocity ratio of 1.33. The starter reproduced this value, while the frozen reference gave 2.63 on the same inputs. A check can therefore agree precisely with a physically incorrect predictor.

The separate delayed-executable pilot used one fresh attempt per task. All three wrote runnable checks. The three repaired predictors received hidden reward 0. The oracle and the completed calibration-fitting shortcut both passed all four generated test cases. None of the three suites distinguished the two controls. [Control replays and saved checks](executable.json)

## Evaluation conditions

The pilot used `gpt-5.6-luna` at high reasoning effort, Codex CLI 0.154.0, Harbor 0.21.0, disabled web search and the benchmark's OpenAI network allowlist. The first three task names alphabetically in the 13-task roster formed the development set. The other ten remain held out. Standard Codex had one 600-second session. The audits had 120, 75, 105 and 300 seconds for derivation, check design, review and repair. Each stage reserved five seconds for process cleanup. The delayed arm hit the design and review deadlines in 14/15 attempts each.

The source branch was `luna-high-qualified-tasks` at `1e9c32e26474` with the local harness changes. The baseline used fresh attempts collected before the corrected audit batch. Nine original setup failures occurred before model execution. Their replacement images used the same scientific packages and an identical Codex executable. Three replacements supplied baseline observations. An early harness sometimes left Codex processes running past a stage deadline. All 30 written audit attempts were rerun after correcting this, with six concurrent trials. The original batch used four and its setup replacements used two.

The final comparison includes 45 graded attempts and 120 confirmed audit-stage cleanups. Public instructions, calibration, public tests and hidden grading came from the frozen roster. The trial records contain the source batch, trial ID, step timings, deadlines and rewards. [Written trial records](written.json)
