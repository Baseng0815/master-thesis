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
| cjson | 15 × 4 | 200 | `CTRL-RAND` |
| libxml2 | 1 × 4 | 400 | none |
| picohttpparser | 1 × 4 | 400 | none |

All three share one 18-table schema, so the extractors are target-agnostic. The
one per-target difference is the name of the `action_rate` series — `json_bytes`
/ `xml_bytes` / `http_bytes` — which `eval_campaigns.py` normalises to the
abstract *structural byte rate*.

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
| `eval_extract.py` | Stage 1: 13 extractors, one CSV each, failure-isolated |
| `eval_figures.py` | Stage 2: 13 figures and 2 tables |

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

Ablations and appendix:

- `ablation-strip` — final coverage of every cjson run, one mark per seed
- `losses` — the five EfficientZero training losses
- `tab-campaign-inventory`, `tab-best-inputs`

## Conventions

Distributions are drawn as a median line inside a quantile band, never as a
mean with a standard deviation, and the ablation figure plots every run
individually. The cjson outcome distribution is not Gaussian, and a mean lands
in a valley where no run lives.

Adding a figure means adding one emitter to `eval_figures.FIGURES`; it gets a
`--only` flag for free. Adding a metric means adding one extractor to
`eval_extract.EXTRACTORS`, then `extract --only <name>`.
