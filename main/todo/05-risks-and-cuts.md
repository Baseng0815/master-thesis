# Risks, cuts, and contingencies

## Cut order — memorise this

When behind at any gate, cut from the bottom. Each line is a decision you have already
made, so that a bad day does not turn into a re-plan.

```
 1. BR-BASE / BR-SIMS1      (branches — redundant now that open62541 supplies real decoys)
 2. S-BS128 / S-BS512       (batch size)
 3. S-SMALL / S-MEDIUM      (model size)
 4. S-ABS1                  (absorbing supervision)
 5. O-CONS0 / O-VP0         (components on open62541 — kept on sequence regardless)
 6. S-LR3e4 or S-LR3e3      (keep 2e-2 — the collapse anchor is the whole point)
 7. S-REAN0                 (reanalyze ratio)
--- below this line the thesis starts losing claims ---
 8. C-BASE                  (cjson — losing this costs the external-validity answer)
 9. O-REW5                  (keep O-REW20: it diagnoses a plateau, the control merely confirms it)
10. S-CONS0 / S-VP0         (losing these costs the EfficientZero-components claim)
11. O-SIMS1 / S-SIMS1       (losing either means no planning claim — do not cut)
12. S-BASE / O-BASE / baselines   (there is no thesis without these)
```

Dropped from the matrix outright, recorded here so the decision is not re-litigated:
`S-SIMS25`/`S-SIMS150` (150 already failed to replicate at −27 % throughput),
`S-TD3`/`S-TD10`, `S-PER05`, `S-NONOISE`, `H-CONS0`/`H-VP0`.

Never cut a **seed** to save time. Nine seeds instead of ten is a wider interval;
skipping a configuration is a missing claim. Cut configurations, keep seed counts.

---

## Risks, ordered by expected damage

### R1 — Seed control turns out to be invasive (D1)

*Symptom:* threading an RNG through the worker threads touches more of the learner than
expected, and D1 becomes D1+D2.

*Mitigation:* the fallback is a **process-level seed**: set the seed once at startup in
each worker thread from `master ^ role_id`, without refactoring ownership. It is less
elegant and less exactly reproducible, but it makes runs *labelled and comparable*,
which is what the protocol needs. Take the fallback at 18:00 on D1 rather than losing
D2.

*Do not* proceed to the campaign with uncontrolled seeds. Every downstream statistical
claim depends on this one item.

### R2 — Code freeze slips (D2)

*Symptom:* the eval probe or the runner is not done on D2 evening.

*Mitigation:* freeze anyway, with whatever landed. A campaign with a weaker metric set
that starts on time beats a perfect metric set that starts on D4. The eval probe can be
approximated from training returns for P0 and added properly for P1 — but then the two
tiers are not comparable, so record which runs have which.

*Hard limit:* one day. A freeze on D3 costs the entire P2 tier.

### R3 — A learner bug is found mid-campaign (D5–D10)

*Symptom:* a genuine correctness bug surfaces after runs have completed.

*Decision rule, decided now:*
- Found **before G3 (D5)**: fix, re-freeze, re-run P0. There is budget for exactly one
  such event.
- Found **after G3**: do **not** fix. Record it as a known limitation in
  `sec:discussion-threats` and keep the results self-consistent. A thesis with a
  documented flaw and consistent numbers is defensible; a thesis with two incomparable
  half-campaigns is not.

This rule exists because the 07-12 campaign already learned it the expensive way: old
code and new code were not comparable, and mixing them wasted the analysis.

### R4 — Runs do not fit two-wide, so the budget is 20 % tighter than hoped

*Mitigation:* already priced in — the matrix is 186 h against 220 h at one-wide. Two-wide
is upside, not the plan. If the D2 pilot shows contention makes 2 runs slower than
1.6× one run, stay single-stream and do not revisit it.

### R5 — `sequence` runs are longer than 2 h in practice

*Symptom:* the historical "2 h slot" was a scheduling choice, not a convergence time,
and runs need 4 h to show the result.

*Mitigation:* measure on D1 with a throwaway run and **re-cost the matrix on D3 before
launching**, not on D8 when it is too late. If a run needs 4 h, the matrix halves:
keep P0 and the P1 component ablations at 5 seeds, drop everything else, and take
`cjson` down to 2 seeds rather than dropping it.

### R6 — Writing does not happen because experiments are interesting

*The most likely failure of this plan.* Nine days of compute run unattended precisely so
that you can write. The gates exist to bound how much time analysis consumes.

*Mitigation:* the writing track in `00-timeline.md` is not optional and is not the
buffer. If a day's writing target slips, cut a P2 configuration to buy the time back —
not the other way round. Every chapter except 12 and 13 can be written **before** the
results exist, and all of them have detailed skeletons already.

### R7 — External validity rests on `cjson` alone

With `open62541` in P0 the target set is no longer thin: it is a real OPC UA stack, and
it is what makes the "stateful" in the title defensible. But note what it does *not*
fix — its reward is still **designed** (`+1` survive, `+10` activate). `cjson` remains
the only target with no reward engineering at all.

So if `C-BASE` is cut, `sec:targets-realistic` still has `open62541` and the thesis is
far from empty — but the answer to *"does this work where you did not shape the
reward?"* becomes "untested", and that must be said in `sec:discussion-threats` rather
than glossed. Three seeds of `cjson` is cheap insurance against the sharpest question
in the defence; protect it ahead of every P2 block.

### R9 — `open62541` plateaus in the self-loop corridor

*Symptom:* `O-BASE` returns cluster at ≈12, never at 14. The agent learned to survive,
not to connect.

*Why it is likely:* looping a self-loop message needs no ordering and pays 12; the
connect path needs an exact 4-step ordering out of ~50 000 and pays 14. Discounted,
≈11.4 vs ≈13.6. The reward margin is 17 % for a needle in a haystack.

*This is not a failure of the plan — it is one of its two possible findings*, and both
are writable:

- **connects** → the stateful navigation claim, with the decoy structure making it a
  strong result,
- **plateaus** → a clean, quotable finding about coverage-and-survival rewards on
  stateful targets: the reward that keeps the agent alive also pays it to do nothing.
  `O-REW20` then shows whether the margin or the learner was the binding constraint,
  and the whole thing lands in `sec:failure-reward-hacking` — which already exists as a
  section because the teardown-burst episode taught the same lesson.

*What is not acceptable:* discovering the plateau on D7 and spending D8–D10 re-tuning
`CONNECTED_REWARD` until it connects. That is fitting the target to the result. Run
`O-REW20`/`O-REW5` as the pre-declared experiment they are, report what happens, and
move on.

*Decision rule for Gate G3b:* whichever way it lands, write that section from the D7
figure (F21, the return distribution with the 12 and 14 lines drawn) and do not revisit.

### R8 — Corpus chapter has no results

Chapter 8 (`fuzzing-corpus-actions/`) and `sec:results-head-to-head` currently assume a
corpus evaluation that this two-week plan does not include.

*Decide on D3, not D12.* Options:
- **a)** Keep Ch 8 as a design-only chapter, explicitly framed as "formulated and
  implemented, not evaluated", and **cut `sec:results-head-to-head`**. Move the
  comparison to future work. This is the honest and cheap option.
- **b)** Buy 3 seeds of `corpus` on cjson (~8 h) in place of a P2 block, giving a
  minimal head-to-head. Only viable if P0+P1 finish early — and note the corpus
  environment has had a scheduler-dependency history, so budget debugging time.

Recommendation: **(a)**, decided on D3 so the introduction and RQs are written once.

---

## Standing checks (cheap, catch expensive mistakes)

- [ ] After the first three runs of every tier: are the seeds actually different, and
      recorded in the `experiments` table?
- [ ] Daily: `df -h` — the campaign writes DBs, logs and `.mpk` checkpoints, and
      `checkpoint_history` keeps every one of them. The 07-12 campaign produced 1.6 MB
      log files *per run* and multi-GB DBs with the data-introspect probes enabled.
      Keep `data_introspect` off for campaign runs.
- [ ] Daily: does `git status` in `~/mugiwara` show a dirty tree? Runs must record a
      clean `git_sha` or the confirmatory claim is unverifiable.
- [ ] At each gate: run-hours consumed vs the plan. Being 20 % over at G3 means cutting
      at G3, not at G4.
