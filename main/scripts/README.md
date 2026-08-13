# Evaluation pipeline

Turns the fuzzing campaigns into the figures and tables of `\ref{chap:results}`.
Everything under `figures/generated/` and `figures/data/` is written by this
pipeline and is safe to delete; the hand-drawn TikZ in `figures/` is not.

```sh
./scripts/evaluate.py runs        # inventory: what would be evaluated
./scripts/evaluate.py extract     # per-run databases -> CSV cache (~25 min)
./scripts/evaluate.py figures     # cache -> figures/data + figures/generated
```

Then `\input` a figure from the chapter that discusses it:

```latex
\input{figures/generated/coverage-executions}
```

## Why two stages

The campaign is roughly 133 GB of SQLite across 68 runs, with single tables
reaching 13 million rows. Querying that per figure would cost minutes per
tweak, so `extract` reads each database exactly once and writes a few hundred
kilobytes of CSV per run; `figures` reads only the cache. The cache lives at
`$DATA_ROOT/_evalcache` — it is derived data and is not committed.

`extract` is incremental. A run whose CSVs already exist is skipped unless
`--force` is passed, so fixing one extractor costs only the work that changed:

```sh
./scripts/evaluate.py extract --only coverage --force
./scripts/evaluate.py figures --only saturation
```

## Standard library only

Deliberate. This script is the provenance of every number in the results
chapter, and it has to still run years from now; a dependency on a
scientific-Python stack that has since moved on would make those numbers
unreproducible. All heavy aggregation happens in sqlite, which is better at it
than Python would be anyway.

## What the campaigns look like

| Target | Arms × seeds | Iterations | Random control |
|---|---|---|---|
| high-and-low | 1 × 1 | 100 | within-run (chance rate) |
| sequence | 1 × 1 | 400 | none |
| cjson | 15 × 4 | 200 | `CTRL-RAND` |
| libxml2 | 1 × 4 | 400 | none |
| picohttpparser | 1 × 4 | 400 | none |

The three corpus targets share one 18-table schema, so the extractors are
target-agnostic across them. The one per-target difference is the name of the
`action_rate` series — `json_bytes` / `xml_bytes` / `http_bytes` — which
`eval_campaigns.py` normalises to the abstract *structural byte rate*.

The two input-level targets are the exception in every one of those respects,
which is why they get their own emitters rather than a panel in the corpus
figures:

- **One run each, one seed.** They are feasibility checks that were stopped
  once the target was solved, not campaigns. Their database sits directly in
  the campaign root instead of in a `LABEL-sNN` run directory, so
  `eval_campaigns.discover` reads them through `read_single_run` and labels the
  arm `MAIN`. Nothing about them carries a seed spread; where their figures
  show a band it is the spread across the 128 environments of one iteration,
  and every caption says so.
- **Fewer probes, and not the same ones.** high-and-low has `action_rate` (its
  series is `high_coverage`) but no `collapse_entropy`; sequence has
  `collapse_entropy`, `depth_action_counts` and `action_tree_*` but no
  `action_rate`. Neither has `run_union`, so neither yields a coverage curve
  and neither appears in `tab-campaign-inventory`.
- **`iteration` is NULL** on their `trajectory` and `loss` tables, as it is on
  the corpus runs', so both are binned on `env_steps` / `train_batches`.

An extractor whose probe a run does not carry is skipped by the `requires`
decorator rather than reported as a failure — an absent probe is not an error,
and without it two healthy runs would report ten.

Because libxml2 and picohttpparser have no random control arm, their claims
rest on the within-run control instead: the structural byte rate at iteration 0
is what an untrained policy achieves, and every structural-rate figure draws
that level explicitly. No figure compares those two targets against a floor
they do not have.

Coverage is never shared across targets on one axis — they instrument different
numbers of basic blocks (picohttpparser 4096, libxml2 16384) and their ranges
differ by two orders of magnitude. Absolute coverage gets one panel per target;
only normalised quantities are overlaid (`saturation`, `structural-decay`).

## Data hygiene

Handled by `eval_campaigns.discover`, and worth knowing when reading the
numbers:

- The aborted development database at the data root (outside any run
  directory, NULL seed) and the `discarded-400bound-*` campaign (runs stopped
  on purpose) are excluded.
- Run metadata comes from each database's `experiments` table, not from the
  directory layout — the cjson campaign has an `evaluation.json` per run and a
  `ledger.jsonl`, the other two have only a `waves.log`. The `experiments` row
  is the one source present everywhere.
- File modification times are **not** metadata. The cjson directories are
  stamped with the date they were rsynced off the training VM (11 August), not
  the date they ran (29 July – 4 August).
- Six runs are short of their nominal length: `T25-s00..s03` (192–198 of 200)
  and `SIMS100-s01,s02` (197–199 of 200). `T25-s03` is additionally still
  marked `running`, because the writer sets that status when the learner drops
  its hooks and its process died first — the campaign ledger records the run as
  completed with a full 21-hour duration. They are all kept, since discarding
  them would drop seeds from the best-performing arm over a bookkeeping
  artefact, but they are reported by `evaluate.py runs` and in
  `tab-campaign-inventory`. Ragged runs are aligned by truncating to the
  shortest, never by padding.
- The three campaigns were built from different revisions, and the
  picohttpparser binary was built from a dirty tree. Worse, **two arms are not
  homogeneous**: libxml2 ran seeds 0,1 on `18a8f75c` and seeds 2,3 on
  `fc8884b2`; picohttpparser ran seeds 0,1 on `c779bccd` and seeds 2,3 on
  `48ea3b48`. Their four seeds are therefore not four samples of one
  configuration. All 15 cjson arms are single-revision. `evaluate.py runs`
  lists the split arms and `tab-campaign-inventory` prints every revision an
  arm used, so neither the table nor the reader can miss it.

## Module layout

| File | Role |
|---|---|
| `evaluate.py` | CLI: `runs`, `extract`, `figures` |
| `eval_campaigns.py` | Campaign discovery, run metadata, config parsing |
| `eval_extract.py` | Stage 1: 15 extractors, one CSV each, failure-isolated |
| `eval_figures.py` | Stage 2: 16 figures and 3 tables |

Extractors are failure-isolated because the schema drifts: the wave-1 cjson
runs predate the `episode_best` probe and have 17 tables where the later runs
have 18. A missing table degrades one CSV, not the run — `best_inputs` falls
back to the `seed` table and records which source it used.

## Figures produced

Headline results:

- `coverage-executions`, `coverage-wallclock` — union coverage against both
  currencies, one panel per target, median and interquartile band
- `structural-rate` — structural byte rate per seed against its chance level
- `return` — per-trajectory return
- `saturation` — coverage normalised to each run's final level, all targets

Mechanism — whether it works *for the reason claimed*:

- `policy-improvement` — KL between the MCTS visit distribution and the policy
  prior. Nothing else in the campaign can say whether planning contributed
- `collapse-entropy` — MCTS visit entropy per episode-step position
- `depth-actions` — the policy-collapse matrix
- `tree-depth` — action-trie breadth by depth

Failure modes:

- `structural-decay` — the peak-then-decay of the structural rate, overlaid
  across targets. The strongest cross-target observation in the campaign
- `buffer-reward-density` — reward sparsity in the replay buffer

Input-level targets — the correctness check that the learner solves a target at
all, reported in their own units because they share no axis with the corpus
targets:

- `input-learning` — episode return per target, beside the evidence that names
  the outcome: the high-coverage byte rate against its measured chance level
  for high-and-low, the episode length against the 16-byte passcode for
  sequence, which because the program exits on the first wrong byte is the
  length of the correct prefix
- `input-entropy` — action entropy against the uniform policy $\ln|\mathcal{A}|$
- `input-losses` — the five training losses on both targets

Ablations and appendix:

- `ablation-strip` — final coverage of every cjson run, one mark per seed
- `losses` — the five EfficientZero training losses
- `tab-campaign-inventory`, `tab-best-inputs`
- `tab-deep-seed` — the campaign's registered primary metric on cjson: the
  share of episodes clearing the 99th percentile of the pooled `CTRL-RAND`
  distribution. The threshold is derived once from all four control runs and
  every arm is scored against that one number, so the `episode_scores`
  extractor keeps a full integer histogram per run rather than a rate against a
  fixed cut — the cut is not known until every control run has been read.
  Reproduces `findings/campaign-cjson-results-2026-08-02.md` digit for digit,
  which is the point: the headline claim now comes from the databases rather
  than from a markdown file.

## Conventions

Distributions are drawn as a median line inside a quantile band, never as a
mean with a standard deviation, and the ablation figure plots every run
individually. The cjson outcome distribution is not Gaussian, and a mean lands
in a valley where no run lives.

A logarithmic ordinate is chosen from the data, never from the name of the
series. pgfplots drops non-positive coordinates of a log axis silently, so a
hard-coded `ymode=log` deletes most of a curve rather than failing: the total
loss carries the consistency loss with a coefficient of two and turns negative
on both input-level targets, though not on any corpus target.

The value loss is a cross-entropy against a two-hot target on a **fixed**
support of the transformed value `h(v) = sign(v)(sqrt(|v|+1) - 1) + 1e-3 v`
(`efficientzero/src/learner/engine/training.rs`), not an MSE. It therefore does
*not* scale with the size of the return, and "the returns grew, so the loss
grew" is not an available explanation. Read it in bins of the support — the
grid is constant, so `value_error_root_mean / bin_width` is the comparable
quantity. Note also that the loss averages over all `rollout_depth` unroll
positions while `value_error_root_mean` covers only the root, so the two can
move in opposite directions, as they do on high-and-low.

`action_entropy` is pooled over episode positions and is *not* a measure of
per-state determinism on a target whose optimal action depends on the position.
A policy that plays each of sequence's 16 passcode bytes deterministically
still pools to about ln 16 = 2.77 against a uniform ln 26 = 3.26, which reads
as a policy that barely converged and is the opposite. Per-state determinism
lives in `collapse_entropy` (per-position visit entropy, 0.13–0.18 nats at the
end of that run) and `depth_action_counts`.

Adding a figure means adding one emitter to `eval_figures.FIGURES`; it gets a
`--only` flag for free. Adding a metric means adding one extractor to
`eval_extract.EXTRACTORS`, then `extract --only <name>`.
