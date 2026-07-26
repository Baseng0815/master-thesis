# Experiment matrix

Every run in the campaign. Total ≈ **222 run-hours**; the D3–D12 queue holds ≈ 220 h at
one run at a time. **P0 + P1 = 162 h and fits comfortably; P2 is 61 h against ~58 h
remaining, so expect to cut roughly one P2 block** — that is what the cut order in
[05-risks-and-cuts.md](05-risks-and-cuts.md) is for. If the D2 concurrency pilot allows
2-wide, all of P2 fits and everything moves up ~2 days.

## Conventions

- **Seed pool is `0..9`, pre-registered** (`todo/seed-pool.txt`), fixed before any
  result is read. Headline configs use all 10. Load-bearing ablations use `0..4`
  **paired** with the same seeds from the headline set — pairing is what makes 5 runs
  yield a defensible comparison (`sec:methodology-seeds`). Peripheral ablations use
  `0..2` and are labelled *indicative* in the thesis.
- **One factor at a time.** Every row changes exactly one thing against the frozen
  baseline config.
- **Label = directory = `config_json.label`.** `runs/<LABEL>-s<NN>/`.

Command template:

```sh
MW_LOG=warn nix develop -c cargo run --release --example open62541 --features cuda -- \
  --train runs/O-CONS0-s03/model \
  --seed 3 --max-iterations <N> \
  --consistency-loss-coeff 0.0
```

## Baseline config (record actual values in `todo/frozen-config.md` at G2)

Library defaults from `efficientzero/src/learner/mod.rs`, plus per-example overrides.
Both `sequence` and `open62541` override the value supports — **those overrides are the
derived hyperparameter** the methodology chapter uses as its worked example, so record
the arithmetic, not just the number. `open62541` documents it in place
(`open62541.rs:374-380`): returns run to ~22, the support covers h(22) ≈ 3.8 at
~0.025-h bin density, which is what keeps the +1 step-reward gap separable →
`DiscretizeSupport::new(-2.0, 4.5, 261)`.

| parameter | default | note |
|---|---|---|
| `learning_rate` | `1e-3` | `2e-2` is the known-bad anchor (NaN PER priorities, run 019f67bc) |
| `batch_size` | `256` | |
| `rollout_depth` | `6` | |
| `td_steps` | `5` | |
| `policy_loss_coeff` / `value_loss_coeff` | `1.0` / `0.25` | |
| `value_prefix_loss_coeff` | `1.0` | |
| `consistency_loss_coeff` | `2.0` | SimSiam |
| `per_reward_coeff` | `0.0` | value-error-only prioritization |
| `model_size` | `Full` | |
| `num_iterations` (MCTS sims) | `100` | **the 07-12 campaign settled on 50 — record what each example sets** |
| discount | `0.99` | |
| `absorbing_state_supervision` / `absorbing_depth` | `false` / `usize::MAX` | |
| `reanalyze_ratio` / `reanalyze_noise` | `1.0` / `true` | `noise=false` has collapsed training before |
| `root_exploration_fraction` / `alpha` | `0.25` / `0.3` | |
| `replay_buffer_capacity` | `10 000` | |
| `transitions_per_iteration` | `512` | |

Per-target facts that drive cost:

| target | actions | obs floats | episode cap | est. h/run |
|---|---|---|---|---|
| `sequence` | 26 | 8 192 (2 × 4096) | 16 | 2.0 |
| `open62541` | 15 | **32 768** (2 × 16384) | 12 | 2.5 *(measure on D1)* |
| `high_and_low` | 256 | — | short | 0.5 |
| `cjson` | small alphabet | — | fixed | 2.5 |
| `branches` | 26 | — | ~7 | 2.0 |

`open62541`'s observation is 4× `sequence`'s, which is the main cost driver; its
episodes are shorter and its action space smaller, which pulls the other way. **The
2.5 h estimate is a guess — measure it on D1 and re-cost this table on D3 before
launching** (risk R5).

---

## P0 — without this there is no thesis (≈ 91 h, D3–D6)

Queue in **this order**, so Gate G3 on D5 has a complete `sequence` picture with its
comparators before the more expensive target starts.

| # | label | target | change | seeds | h/run | total |
|---|---|---|---|---|---|---|
| 1 | `S-BASE` | sequence | — (frozen baseline) | 0–9 | 2.0 | 20.0 |
| 2 | `S-CLIMB` | sequence | coverage-guided climber | 0–9 | 0.35 | 3.5 |
| 3 | `S-RAND` | sequence | random policy | 0–9 | 0.2 | 2.0 |
| 4 | `S-ORACLE` | sequence | `--optimal` | 0–2 | 0.2 | 0.6 |
| 5 | `S-SIMS1` | sequence | `--num-iterations 1` | 0–4 | 2.0 | 10.0 |
| 6 | `O-BASE` | open62541 | — (frozen baseline) | 0–9 | 2.5 | 25.0 |
| 7 | `O-CLIMB` | open62541 | coverage-guided climber | 0–9 | 0.4 | 4.0 |
| 8 | `O-RAND` | open62541 | random policy | 0–9 | 0.3 | 3.0 |
| 9 | `O-ORACLE` | open62541 | `--optimal` (the connect path) | 0–2 | 0.3 | 0.9 |
| 10 | `O-SIMS1` | open62541 | `--num-iterations 1` | 0–4 | 2.5 | 12.5 |
| 11 | `H-BASE` | high_and_low | — | 0–9 | 0.5 | 5.0 |
| 12 | `H-SIMS1` | high_and_low | `--num-iterations 1` | 0–4 | 0.5 | 2.5 |
| 13 | `H-RAND` / `H-CLIMB` | high_and_low | baselines | 0–9 | 0.1 | 2.0 |

**`S-SIMS1` and `O-SIMS1` are the most important non-baseline runs in the campaign.**
They are the only thing separating "planning helps" from "a learned value function over
coverage helps", and no claim about planning may appear in the thesis without them
(`sec:discussion-threats` #3). `O-SIMS1` is the stronger of the two: `open62541` has a
real decoy structure, so lookahead should matter there if it matters anywhere.

**`O-CLIMB` is the interesting baseline.** A coverage-guided climber on `open62541`
will happily sit in the self-loop corridor collecting `+1`/step. If the RL agent does
the same thing, that is the headline finding about coverage-as-reward on a stateful
target — report it, do not bury it.

---

## P1 — mechanism, sensitivity and external validity (≈ 70 h, D7–D9)

### EfficientZero component ablations — on `sequence`

*Does this piece of EfficientZero's sample-efficiency machinery earn its keep in this
domain, or is it Atari-specific?* Paired seeds `0..4`. Run on `sequence` because it is
the calibration target with the most legible progress axis; the `open62541` versions
are P2.

| label | change | h/run | total |
|---|---|---|---|
| `S-CONS0` | `--consistency-loss-coeff 0.0` (SimSiam off) | 2.0 | 10.0 |
| `S-VP0` | `--value-prefix-loss-coeff 0.0` (value prefix off) | 2.0 | 10.0 |
| `S-REAN0` | `--reanalyze-ratio 0.0` (stored self-play targets only) | 2.0 | 10.0 |

`consistency_loss_coeff 0.5` was already tried in the 07-12 campaign and *reshaped
rather than fixed* — heads decoupled, policy entrenched confident-wrong. Use **0.0**:
the question is presence/absence, not a coefficient sweep.

### The `open62541` reward-margin experiment — **run this**

The designed experiment that follows from the 12-vs-14 trap (README, decision 2). Three
seeds each, changing only `CONNECTED_REWARD`:

| label | `CONNECTED_REWARD` | survive vs connect | seeds | total |
|---|---|---|---|---|
| `O-REW20` | `20.0` | 12 vs 24 | 0–2 | 7.5 |
| `O-REW5` | `5.0` | 12 vs 9 — **goal is now worse than loitering** | 0–2 | 7.5 |

Falsifiable prediction to write down *before* running: if `O-BASE` plateaus at return
≈12 and `O-REW20` reaches the connect path, the failure is the reward margin, not the
learner — and that is a clean, quotable result about coverage-and-survival rewards on
stateful targets. `O-REW5` is the negative control: the agent *should* loiter, and if
it connects anyway the margin was never the binding constraint.

This requires a recompile (the constant is not a CLI flag). Either promote
`CONNECTED_REWARD` to an env var / flag during the D1–D2 infra window, or accept three
binaries. **A constant change in an example is not a learner change**, so it does not
violate the code freeze — but record which binary each run used.

### Learning-rate sensitivity

Baseline `1e-3` is covered by `S-BASE`. Three further points × 3 seeds:

| label | `--learning-rate` | seeds | total |
|---|---|---|---|
| `S-LR3e4` | `3e-4` | 0–2 | 6.0 |
| `S-LR3e3` | `3e-3` | 0–2 | 6.0 |
| `S-LR2e2` | `2e-2` | 0–2 | 6.0 |

`2e-2` is the **known-bad anchor** (NaN PER priorities → collapse, run 019f67bc).
Including it turns the LR justification from "the paper used this" into "we observed
instability at 2e-2 and a stable basin around 1e-3" — the difference between an
inherited and an empirically validated hyperparameter.

### Raw-coverage external validity

| label | target | change | seeds | h/run | total |
|---|---|---|---|---|---|
| `C-BASE` | cjson | frozen config, transferred unchanged | 0–2 | 2.5 | 7.5 |

The only planned target with **no designed reward**. Three seeds is thin, but it is the
only evidence that speaks to *"does this survive on a target you did not design?"*
**Transfer discipline:** the frozen `sequence` config applied unchanged. Do not tune it.
If it fails, that failure *is* the answer to RQ4 — report it.

---

## P2 — depth, only if P0+P1 are complete at Gate G4 (≈ 61 h, D10–D11)

| label | target | change | seeds | total |
|---|---|---|---|---|
| `S-ABS1` | sequence | `--absorbing-state-supervision true --absorbing-depth 1` | 0–4 | 10.0 |
| `O-CONS0` / `O-VP0` | open62541 | component ablations on the stateful target | 0–2 | 15.0 |
| `BR-BASE` / `BR-SIMS1` | branches | planning test on the synthetic maze | 0–2 | 12.0 |
| `S-BS128` / `S-BS512` | sequence | `--batch-size 128` / `512` | 0–2 | 12.0 |
| `S-SMALL` / `S-MEDIUM` | sequence | `--model-size small` / `medium` | 0–2 | 12.0 |

Notes:

- **Absorbing supervision is off by default**, so `S-ABS1` turns it *on*. Depth 1 is the
  interesting setting: the first absorbing position carries the discrimination signal,
  while supervising all of them floods the losses with exact-zero targets. This is the
  "absorption rate" lever and it is tied to the dead-branch failure mode
  (`sec:failure-dead-branch`).
- Batch size and model size are the parameters most exposed to the "the paper did it"
  objection, since Atari-100k is far from this domain. If only one P2 block survives,
  take these two.
- `sims` sweeps (25/150), `td_steps` and `per_reward_coeff` are **dropped from the
  matrix entirely**: `sims=150` already failed to replicate at −27 % throughput in the
  07-12 campaign, and the rest are the lowest-value rows. They stay in the cut list only
  as a record of the decision.

---

## Queue files

Split by tier so a cut at Gate G4 is one deleted file, not a re-plan:

```
~/mugiwara/queues/p0.txt
~/mugiwara/queues/p1.txt
~/mugiwara/queues/p2.txt
```

One line per run, in queue order:

```
S-BASE     sequence   0
O-CONS0    open62541  3  --consistency-loss-coeff 0.0
```

Use **one DB per target** (`sequence-experiments.db`, `open62541-experiments.db`, …) —
every run inserts its own `experiments` row with a UUID and each metric row carries
`experiment_id`, so runs stay separable within a target. If the queue runs 2-wide, use
one DB per run and merge at analysis time.

## Running total

| tier | run-hours | drains by |
|---|---|---|
| P0 | 91 | D6 (07-30) |
| P1 | 70 | D9 (08-02) |
| P2 | 61 | D11 (08-04), partially |
| **total** | **222** | vs ~220 h available |
