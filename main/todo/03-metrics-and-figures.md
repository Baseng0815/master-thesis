# Metrics and figures

Every figure has a destination in the thesis. If a plot has no destination, do not make
it — with dozens of diagnostic series available, plotting is the easiest way to lose a
day. Section labels below are the ones in the restructured thesis.

## Headline figures — Ch 12 *Results*

| # | figure | source | destination |
|---|---|---|---|
| F1 | max solve depth vs environment steps; RL / climber / random / oracle on one axis, median + IQR over 10 seeds | eval probe (§3 infra) | `sec:results-input-actions` |
| F2 | solve rate over training, windowed, with Wilson interval | eval probe | `sec:results-input-actions` |
| F3 | executions-to-first-solve and to-stable-solve, per seed (dot plot, not bars) | eval probe | `sec:results-input-actions` |
| F4 | first-passage time per depth — executions to first reach depth *k* | `action_tree_nodes.first_env_steps` | `sec:results-input-actions` |
| F5 | full MCTS vs `sims=1`, paired per seed | `S-BASE` vs `S-SIMS1` | `sec:results-ablations` — **the planning claim** |
| F6 | high_and_low: high-coverage-arm rate vs steps | eval probe | `sec:results-input-actions` |
| F7 | coverage vs executions, cjson, RL vs climber vs random | run-level discovery curve | `sec:results-input-actions` (the raw-coverage claim) |
| F8 | branches: which goal is reached, full MCTS vs `sims=1` (P2) | eval probe | `sec:results-ablations` |

### open62541 — the stateful target

| # | figure | source | destination |
|---|---|---|---|
| F20 | **session-activation rate vs environment steps**, RL / climber / random / oracle | eval probe | `sec:results-input-actions` — the headline stateful result |
| F21 | **return distribution across seeds, with the 12 and 14 lines drawn** | `trajectory.return` | `sec:results-input-actions` — the single most informative plot on this target: it shows at a glance whether the agent found the connect path or settled in the self-loop corridor |
| F22 | connect-path depth reached (0–4) over training, per seed | eval probe | `sec:results-input-actions` |
| F23 | per-depth policy/value ranking of the correct message along `hel → opn → create_sess → activate_sess` | `ModelIntrospectProbe` (already wired) | mechanism figure, `sec:results-input-actions` |
| F24 | action-frequency heatmap over training, 15 messages × depth — does mass concentrate on self-loops? | `CollapseProbe` (already attached, `open62541.rs:517`) | `sec:failure-echo-chamber` |
| F25 | `CONNECTED_REWARD` ∈ {5, 10, 20}: activation rate | `O-REW5` / `O-BASE` / `O-REW20` | `sec:results-ablations` — the reward-margin experiment |

F1, F5, F20 and F21 are the figures the thesis cannot ship without. F21 in particular is
cheap and decides how the whole `open62541` section is written, so make it on D7 at Gate
G3b before writing anything about that target.

## Mechanism figures — Ch 12 and Ch 13

These answer *why*, and they are what the probe suite exists for. "It works" and "it
works for the reason claimed" are separate claims, and only these separate them.

| # | figure | probe | destination |
|---|---|---|---|
| F9 | per-depth value and value-prefix ranking of the correct byte over training | `ModelIntrospectProbe` | `sec:results-input-actions` |
| F10 | policy prior vs depth over iterations | `ModelIntrospectProbe` (`introspect_policy`) | `sec:results-input-actions` |
| F11 | policy-collapse matrix (per-position argmax over training) | `CollapseProbe` — **attach it, it is implemented but not in the probe vector** | `sec:failure-echo-chamber` |
| F12 | MCTS visit-count entropy per depth | `CollapseProbe` | `sec:failure-echo-chamber` |
| F13 | value calibration: predicted root value vs realized return | `value_error_root_mean`, upgraded to a reliability plot | `sec:failure-dead-branch` |
| F14 | loss curves, value-prefix and SimSiam highlighted | `LossProbe` | appendix, referenced from Ch 12 |
| F15 | PER points-at-signal: `rewarded_priority_share`, `rewarded_root_share` | `BufferStateProbe`, `SampledBatchProbe` | `sec:failure-value-prefix` |

## Ablation figures — `sec:results-ablations`

| # | figure | destination |
|---|---|---|
| F16 | component ablations: `S-BASE` / `S-CONS0` / `S-VP0` / `S-REAN0` / `S-ABS1`, paired per seed, solve depth | main text |
| F17 | learning-rate sweep, 4 points × 3 seeds, with the 2e-2 collapse anchor visible | main text — the hyperparameter-justification exhibit |
| F18 | batch size and model size (P2) | appendix unless they move the result |
| F19 | cross-target transfer: the frozen config on sequence / branches / cjson | main text — the "you tuned to your result" answer |

## Plotting rules

1. **x-axis is environment steps (executions)** for every learning curve. Add a
   wall-clock twin axis, or a companion figure, for any efficiency claim
   (`sec:methodology-currencies`).
2. **Never mean ± std.** The outcome is bimodal — a run solves or collapses — so the
   mean lands in a valley where no run lives. Use median + IQR, or plot all seeds as
   spaghetti. This is stated as methodology in `sec:methodology-seeds`; the figures
   have to actually obey it.
3. **Oracle ceiling and random floor on every headline axis.** A curve without its
   bounds is unreadable to an examiner who does not know the target.
4. **One colour per configuration across the whole thesis.** Decide the mapping once,
   in the plotting script, not per figure.
5. **Every figure regenerable from a script + a DB in `findings/final/`.** You will
   regenerate all of them at least twice.
6. **Say what was dropped.** If a curve shows 8 of 10 seeds because two crashed, the
   caption says so.

## Tables

| # | table | destination |
|---|---|---|
| T1 | frozen hyperparameter configuration, annotated by justification tier | App. A, referenced from `sec:methodology-hyperparameters` |
| T2 | target ladder: capability isolated / formulation / reward source / role | `sec:targets-overview` |
| T3 | headline results: per target, solve rate + Wilson CI, executions-to-solve (median, conditional on success), wall-clock | `sec:results-input-actions` |
| T4 | paired ablation table: effect size + Wilcoxon/McNemar per ablation | `sec:results-ablations` |

## Scripts

`~/mugiwara/scripts/` already has `plot-model-introspect.py` and
`plot-action-introspect.py`. Extend rather than restart. Add:

- `plot-solve-curve.py` — F1, F2, F6, F8 (takes a list of labels, plots median + IQR),
- `plot-paired-ablation.py` — F5, F16, F17 (paired per-seed differences + the test),
- `plot-coverage-curve.py` — F7,
- `export-tables.py` — T3, T4 straight to LaTeX `booktabs`, so numbers are never retyped.

Writing numbers by hand into LaTeX is how a results chapter and its figures end up
disagreeing. Generate T3 and T4.
