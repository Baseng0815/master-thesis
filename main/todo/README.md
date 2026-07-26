# Experiment & Evaluation Plan — fuzzing-input-actions

Scope: the **input-level action space** (one input symbol per step) evaluated on the
targets in `~/mugiwara/examples/`. Everything here is designed backwards from a
submission on **Saturday 2026-08-08**, starting **Saturday 2026-07-25**.

| file | what it is |
|---|---|
| [00-timeline.md](00-timeline.md) | day-by-day schedule, gates, parallel writing track |
| [01-infrastructure.md](01-infrastructure.md) | code that must land before any campaign run — the critical path |
| [02-experiment-matrix.md](02-experiment-matrix.md) | every run: config, seeds, cost, priority tier |
| [03-metrics-and-figures.md](03-metrics-and-figures.md) | what to measure, which figure goes in which thesis section |
| [04-analysis-protocol.md](04-analysis-protocol.md) | statistics, and how to write up a bimodal outcome |
| [05-risks-and-cuts.md](05-risks-and-cuts.md) | what to drop first when behind, and the decision dates |
| [frozen-config.md](frozen-config.md) | fill at the code-freeze gate; becomes Appendix A |
| `seed-pool.txt` | the pre-registered seeds `0..9` — written before any result is read |

## The plan in one paragraph

Two days of infrastructure (seed control, run-length bound, a queue runner, an
eval-mode probe, instrumentation for `high_and_low`), then a **hard code freeze** on
2026-07-26. From 07-27 the GPU runs unattended around the clock off a queue file while
you write. Runs are tiered P0/P1/P2; P0 alone is a defensible thesis. Experiment
freeze on 2026-08-05, leaving three days for analysis, figures and final writing.

## Targets in scope

All five are **input-level** (one input symbol per step) and all five already exist in
`~/mugiwara/examples/`:

| target | what it is | reward | tier |
|---|---|---|---|
| `sequence` | 16-byte combination lock | designed (living + terminal coverage) | P0 — the calibration instrument |
| `open62541` | real OPC UA stack, 15 message actions, 4-step connect path | designed (+1 survive, +10 activate) | P0 — carries the "stateful" claim |
| `high_and_low` | single-step coverage choice | coverage | P0 — sanity rung |
| `cjson` | JSON parser, byte alphabet | **raw coverage, unshaped** | P1 — external validity |
| `branches` | synthetic DAG maze | designed | P2 — redundant with `open62541` |

## Three things to decide today, before any of it matters

**1. There is no seed control.** `rand::rng()` is called at
`efficientzero/src/utility/mod.rs:41`, `:99` and
`learner/replay_buffer/sample.rs:328`; `sequence.rs:410` seeds its environment RNG
from it too. Every run today draws fresh entropy, and `ExperimentSpec.seed` is
literally `None` (`examples/sequence.rs:471`). The multi-seed protocol the evaluation
chapter is built on — pre-registered pool, paired comparisons, per-seed reporting —
**cannot be run until this is fixed**. It is item 1 of
[01-infrastructure.md](01-infrastructure.md) and it blocks everything else.

**2. `open62541` carries the thesis title and belongs in P0.** `high_and_low` and
`sequence` are both *diagnostic microbenchmarks* with hand-shaped rewards; a thesis
evaluated only on them meets the strongest objection in
`chapters/discussion/threats.tex` with nothing. `open62541` is the target that answers
it: a real OPC UA stack under emulation, 15 protocol-message actions, and a 4-step
connect path (`hel → opn → create_sess → activate_sess`) that is exactly the stateful
navigation the title claims. It is already instrumented with the full probe set — and
unlike `sequence` it already has `CollapseProbe` attached (`open62541.rs:517`) — and it
was verified end to end against the real emulated server, with coverage tracking
protocol progress (hel ≈ 391 blocks → create_sess ≈ 2573). It is P0 in the matrix.

Two further input-level targets exist and cost nothing to build:

- `cjson.rs` — **raw coverage, no designed reward at all**; the only planned target
  where the reward was not engineered, so it is the cleanest answer to *"does this
  survive on a target you did not design?"* P1, three seeds.
- `branches.rs` — the synthetic DAG maze. Demoted to P2: `open62541` now supplies a
  *real* decoy structure (see below), which makes the synthetic one largely redundant.

**Watch the `open62541` reward margin.** With `LIVING_REWARD = 1.0`,
`CONNECTED_REWARD = 10.0` and `MAX_EPISODE_STEPS = 12`, a policy that loops any
self-loop message (`get_ep`, `find_srv`, `read_req` all survive without advancing)
scores **12** for free, while the connect path scores **14** but requires an exact
4-step ordering out of 15⁴ ≈ 50 000. Discounted: ≈11.4 vs ≈13.6. That is a genuine
local-optimum trap and the most interesting experiment on this target — but it also
predicts runs plateauing at 12. `O-REW*` in the matrix tests it directly.

**3. No corpus-level results means Chapter 8 is design-only.**

The restructured thesis
has `chapters/fuzzing-corpus-actions/` as a full chapter and
`sec:results-head-to-head` as the controlled comparison. If the corpus branch stays
out of scope, that chapter becomes a design contribution with no evaluation, and
`sec:results-head-to-head` must be cut. That is a legitimate choice — but decide it
now, not on 2026-08-05, because it changes the introduction, the research questions
and the title.

## Working rules for the two weeks

1. **Freeze the code on 2026-07-26.** Every P0 run is confirmatory from the start.
   A learner change after the freeze invalidates every completed run — see
   `sec:methodology-preregistration`.
2. **Pre-register the seed pool** (`0..9`) before looking at any result. Write it into
   `todo/seed-pool.txt` and never deviate.
3. **The GPU is never idle.** Anything that requires you to watch it is a bug in the
   runner, not a task.
4. **One finding file per campaign day** in `~/mugiwara/findings/`, named by date.
   Analysis you do not write down on the day is analysis you will redo.
5. **Never mix pre- and post-freeze numbers** in one plot.
