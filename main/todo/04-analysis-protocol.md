# Analysis protocol

Decided before the data arrives, so that analysis choices cannot be fitted to results.
This file is also the source for `chapters/methodology.tex` — write that chapter from
here on D5, before the results tempt you.

## 1. The outcome is bimodal, and that changes everything

A run either learns the task or collapses. That is a mixture of two populations, not
Gaussian noise around a mean. Consequences, all of them binding:

- **Primary metric is a rate**, not an average: fraction of seeds that solve.
- **Interval is Wilson**, not the normal approximation — N is 10 and p sits near 0 or 1.
  Report the width honestly: 8/10 gives roughly [0.49, 0.94]. The width is a result.
- **Continuous metrics are reported conditional on success**: "of the seeds that
  solved, median executions-to-solve was X". Never blend solvers and collapses into one
  average.
- **Curves are median + IQR, or all seeds plotted.** Never mean ± ribbon.

## 2. Variance here is algorithmic, not environmental

The environment is deterministic (verify it — `sec:platform-determinism`: same input,
identical block-coverage vector, no address drift, clean snapshot restore). So all
run-to-run variance comes from initialization, MCTS Dirichlet noise, PER sampling and
data-collection RNG. State this explicitly: it makes the campaign a **reliability study
of the learner**, which is a stronger framing than apologising for noise.

If §1 of the infrastructure work shows that identical seeds do not reproduce
bit-for-bit (GPU accumulation order, worker scheduling), say so and treat the residual
as part of algorithmic variance. Do not claim reproducibility you did not verify.

## 3. Paired comparison is what makes 5 seeds enough

Every ablation runs on the **same seeds** as the baseline subset, and is compared
per-seed. Differencing out between-seed variance is why 5 paired runs can support a
conclusion that 5 unpaired runs cannot.

| comparison | test |
|---|---|
| solve rate (baseline vs ablation, paired) | McNemar, or a paired bootstrap |
| executions-to-solve, depth reached (paired) | Wilcoxon signed-rank — small N, non-normal, not a t-test |
| effect size | report the difference itself (Δ solve rate, Δ median executions), always |

**Report effect sizes, not p-values alone.** With N=5 nothing will be significant; the
honest statement is "the difference is Δ, which lies inside/outside the seed band".

**If the effect falls inside the seed band, report insensitivity.** That is a finding,
and for a hyperparameter it is a *stronger* justification than a tuned value: it says
the conclusion is not an artifact of the choice — which is the question an examiner is
actually asking (`sec:methodology-hyperparameters`).

## 4. Attribution: what does the work?

The single most likely challenge is that the win comes from a learned value function
over coverage rather than from planning. The protocol:

- `S-BASE` vs `S-SIMS1`, paired, on both `sequence` and `branches`.
- If `sims=1` roughly matches full MCTS, the contribution is **"learned value over
  coverage"** and the thesis says so in those words. That is still a result — it is
  just a different one, and claiming planning without this evidence is the kind of
  thing that does not survive a defence.
- Secondary evidence: policy-improvement (KL between the MCTS visit-count policy and
  the network prior at the root). If search merely echoes the prior, it is not
  improving it, and that supports the same conclusion mechanistically.

## 4b. `open62541`: define "success" before looking

The outcome on this target is not binary in the way `sequence`'s is, so fix the
definitions now:

- **Primary metric: session-activation rate** across seeds — did the run reach the
  connected state under greedy evaluation? Wilson interval, same as everywhere else.
- **Secondary: connect-path depth reached** (0–4). A run that reliably gets `hel → opn`
  and stalls at `create_sess` is a different result from one that never leaves `hel`,
  and the per-depth breakdown is what distinguishes them.
- **Report the return distribution against both reference lines**: 12 (loiter in the
  self-loop corridor for the full episode cap) and 14 (connect). A mean return of 12.6
  is meaningless without them; with them it says "most seeds loiter, some connect".
- **Do not** report "coverage reached" as the headline here. Self-loop messages accrue
  coverage without protocol progress, so coverage and task success come apart on this
  target — which is itself worth one sentence in the results, because it is a concrete
  instance of the coverage-is-only-a-proxy argument from `sec:fuzzing-limitations`.

Pre-declared prediction (write it in the finding file on D7 *before* plotting): if
`O-BASE` clusters at ≈12 and `O-REW20` reaches the connect path, the binding constraint
was the reward margin, not the learner.

## 5. Collapse taxonomy — classify, do not average

Every failed seed gets classified, not discarded:

| mode | signature | probe |
|---|---|---|
| echo chamber | prior narrows, search follows prior, visit-count entropy drops | `CollapseProbe`, policy-improvement KL |
| dead-branch value fantasy | value assigned to terminating branches; calibration diverges | `ModelIntrospectProbe`, value-error |
| value-prefix inversion / support pathology | correct action ranked below chance at a depth; support saturated | `ModelIntrospectProbe` |
| reward hacking | return rises while task progress does not | return vs eval-depth divergence |

Report the **distribution over modes**, and note that some failures will be
unclassifiable with current probes — the limits of the diagnostic method are part of
the contribution (`sec:failure-procedure`).

Two distinctions to keep straight, both of which have bitten this project:

- **"ever reached depth k"** vs **"still solving at the end of training"**. Late
  collapse wipes earlier success. Terminal success is the headline; ever-reached is
  reported separately; and you must say *when* the reported model was snapshotted.
- **Excursions vs collapse.** The 07-12 campaign found discrete, full-depth competence
  losses that always healed (28/28 in the 4 h run, mean duration 54–86 iterations).
  Those are not collapses. Define the detector once, apply it uniformly, and state the
  definition — earlier per-report definitions disagreed with each other.

## 6. Exploratory vs confirmatory

Everything in `findings/` before the code freeze is **exploratory** — it generated the
hypotheses. Anything discovered by that search is contaminated as a tested claim, and
with dozens of diagnostic series some will look significant by chance.

Every headline claim is re-run fresh, post-freeze, on the pre-registered pool, and
reported as confirmatory. **Never plot pre-freeze and post-freeze numbers on the same
axes** — the 07-12 campaign already established that old-code and new-code runs are not
comparable (the merge changed stability outright).

## 7. Order of analysis at each gate

1. Did the runs complete? Count crashes and exclusions *before* looking at outcomes.
2. Solve rate + interval per configuration.
3. Paired differences vs baseline, with effect sizes.
4. Mechanism figures for the configurations that differ.
5. Classify failures.
6. Write it into `findings/campaign-<date>-<tier>.md` **the same day**.

## 8. What honest reporting looks like here

- If P0 shows a low solve rate, the thesis is the failure taxonomy plus the diagnostic
  method. Say that in the abstract rather than burying it.
- If `sims=1` matches, retitle the claim, do not requalify the evidence.
- If the frozen config fails on `cjson`, that is the external-validity finding — report
  it as the answer to RQ4, not as a footnote.
- Report both currencies for every efficiency claim: executions-to-solve flatters this
  approach, wall-clock flatters a conventional fuzzer, and naming which one a claim
  rests on is the difference between a defensible and an indefensible sentence.
