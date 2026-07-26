# Timeline — 2026-07-25 → 2026-08-08

Two tracks run in parallel from D3: the **GPU track** is unattended (a queue runner
drains the matrix), the **you track** is writing and analysis. The GPU track only needs
attention at the gates.

Compute assumptions, to be replaced with measurements on D1 and re-costed on D3:

- one RTX 5080, 16 GB; 32-thread Ryzen; historically **one run at a time**,
- `sequence` ≈ **2 h** (the 07-12 campaign ran 2 h slots; its 4 h run reached ~44.8k
  train batches),
- `open62541` ≈ **2.5 h, unverified** — its observation is 32 768 floats, 4× `sequence`,
  but its episodes are shorter (12 vs 16 steps) and its action space smaller (15 vs 26).
  **This number drives 37 h of P0; measure it first.**
- `high_and_low` ≈ 0.5 h, `cjson` ≈ 2.5 h, `branches` ≈ 2 h,
- 24 h/day from D3 to D12 ≈ **220 run-hours**. The matrix is 222 h, of which P0+P1 is
  162 h. P0+P1 fits with slack; P2 is expected to be cut by roughly one block.

---

## D1 — Sat 07-25 · infrastructure sprint (1/2)

**GPU:** timing runs only.

- [ ] **Seed control end to end** — `01-infrastructure.md` §1. The single blocking item.
- [ ] **Run-length bound** — `01-infrastructure.md` §2. Without it the queue cannot advance.
- [ ] **`open62541` smoke test** — `01-infrastructure.md` §7. The test case is present
      again (`~/fuzzing-test-cases/test-cases/open62541`) and a built sysroot exists at
      `~/fuzzing-test-cases-o62/built/open62541`, but the 07-13 notes describe a Docker
      build via `build.rs`. Verify `--evaluate --optimal` still walks
      `hel → opn → create_sess → activate_sess` **today**, not on D6.
- [ ] **Time one `sequence` and one `open62541` run** to a fixed iteration count and
      re-cost the matrix. 37 h of P0 rides on the `open62541` estimate.
- [ ] Populate `ExperimentSpec.seed` / `git_sha` / a `label` in `config_json`
      (`sequence.rs:468`, and the same in `open62541.rs`).
- [ ] Write `todo/seed-pool.txt` = `0 1 2 3 4 5 6 7 8 9`. *(done)*

**Gate G1 (end of day):** a run launched twice with `--seed 3` produces the same return
curve, **and** `open62541 --optimal` reaches the connected state. If either fails, stop
and fix — everything downstream assumes both.

## D2 — Sun 07-26 · infrastructure sprint (2/2) · **CODE FREEZE**

**GPU:** pilot runs only (throwaway).

- [ ] **Eval-mode probe** — `01-infrastructure.md` §3. Highest-value metric gap.
- [ ] **`high_and_low` instrumentation** — `01-infrastructure.md` §4. It has *no*
      experiment writer and *no* probes today.
- [ ] **Queue runner** — `01-infrastructure.md` §5.
- [ ] Attach `CollapseProbe` to `sequence.rs` (implemented, not in its probe vector;
      `open62541.rs:517` already has it).
- [ ] Promote `CONNECTED_REWARD` to a flag or env var so the P1 reward-margin
      experiment does not need three binaries.
- [ ] Concurrency pilot: 1 vs 2 concurrent runs. If 2 cost less than 1.6× the wall-clock
      of one, the queue runs 2-wide and all of P2 fits.

**Gate G2 (23:59) — CODE FREEZE.** `git tag -a freeze-2026-07-26`; record SHAs in
`todo/frozen-config.md`. After this, changes to `~/efficientzero` or to the environments
invalidate completed runs. Plotting scripts, the climber baseline and analysis code stay
unfrozen; so does a reward *constant* in an example, provided you record which binary
each run used.

## D3 — Mon 07-27 · P0 launch · writing starts

**GPU:** P0 queue starts (91 h, drains to D6). Queue order is fixed in the matrix:
`sequence` and its baselines first, so G3 has a complete picture on D5.

- [ ] Re-cost the matrix with D1's measurements **before** launching.
- [ ] Load `queues/p0.txt`, launch, walk away.
- [ ] Coverage-guided climber baseline (`01-infrastructure.md` §6) — does not touch the
      learner, so it may land after the freeze. Needed by queue position 2, so it must be
      ready today.
- [ ] **Decide the corpus-chapter question** (README, decision 3) so the introduction and
      RQs get written once.
- [ ] **Write:** Ch 5 *Platform*, Ch 6 *Fuzzing as an MDP*. Both results-independent.

## D4 — Tue 07-28

**GPU:** P0 — `sequence` block finishing, `open62541` block starting.

- [ ] **Write:** Ch 7 *Input-Level Action Spaces* (all six sections).
- [ ] Sanity-check finished runs: distinct seeds recorded, eval probe writing rows,
      `wall_ms` sane. Do not draw conclusions yet.

## D5 — Wed 07-29 · **Gate G3: is there a `sequence` result?**

**GPU:** P0 continues (`open62541`).

- [ ] Analyse the `sequence` block: solve rate over 10 seeds with a Wilson interval;
      `S-BASE` vs `S-SIMS1` paired.
- [ ] **Decide the narrative** — three cases, all publishable, but they lead to different
      theses. Pick one and stop hedging:
      - a) solves reliably **and** `sims=1` is clearly worse → "planning for fuzzing"; RQ3 positive,
      - b) solves reliably, `sims=1` matches → "learned value over coverage"; retitle the claim, keep the result,
      - c) bimodal or fails → the thesis is the **failure taxonomy** (Ch 13) plus the diagnosis method.
- [ ] `findings/campaign-2026-07-29-p0-sequence.md`.
- [ ] **Write:** Ch 11 *Methodology* — from this plan, before results tempt you to fit it.

## D6 — Thu 07-30

**GPU:** P0 finishes.

- [ ] **Write:** Ch 2 *Background* prose from the existing outline (largest single
      writing job — 375 lines of bullets in `background/fuzzing.tex`).

## D7 — Fri 07-31 · **Gate G3b: does the stateful target work?**

**GPU:** P1 queue starts (70 h, drains to D9).

- [ ] Analyse `open62541`: activation rate across seeds, `O-BASE` vs `O-SIMS1`, and the
      question that decides how this target is written up — **does the agent reach the
      connect path, or does it settle in the self-loop corridor at return ≈12?**
      Either answer is a result; they are different chapters.
- [ ] `findings/campaign-2026-07-31-p0-open62541.md`.
- [ ] **Write:** Ch 4 *Related Work*, Ch 9 *Implementation*.
- [ ] Add the 13 missing bib entries via Zotero (AFLNet, SGFuzz, Klees, CollAFL, AFLGo,
      AFLFast, AFL, QEMU, Unicorn, ASan, Watkins, Williams) — cited as `\todo{cite:}` today.

## D8 — Sat 08-01 · **Gate G4: mid-point triage**

**GPU:** P1 continues.

- [ ] Recount run-hours spent vs remaining. If P1 will not finish by D9, cut per
      [05-risks-and-cuts.md](05-risks-and-cuts.md) — do not extend into writing days.
- [ ] **Write:** Ch 10 *Targets* (configs are fixed now, so it can be written accurately).

## D9 — Sun 08-02

**GPU:** P1 finishes; P2 starts *only if* P0+P1 are complete and analysed.

- [ ] Generate every figure in [03-metrics-and-figures.md](03-metrics-and-figures.md) as
      a **draft**. Do not wait for the last run — a figure that exists is one you can
      write around.
- [ ] **Write:** Ch 12 *Results* §12.1 (input-level).

## D10 — Mon 08-03

**GPU:** P2.

- [ ] **Write:** Ch 13 *Failure Modes* — the collapse taxonomy, evidenced from the DBs.

## D11 — Tue 08-04

**GPU:** last queue slots. **Anything not started by 12:00 today will not finish.**

- [ ] **Write:** Ch 12 §12.4 *Ablations*.
- [ ] Final figure pass with complete data.

## D12 — Wed 08-05 · **Gate G5: EXPERIMENT FREEZE**

**GPU:** stops. Nothing new is launched after today, whatever the result.

- [ ] Export the DBs behind the final figures to `findings/final/` so plots regenerate.
- [ ] Fill the frozen-configuration table (App. A) from `todo/frozen-config.md`.
- [ ] **Write:** Ch 14 *Discussion* (advantages, limitations, threats).

## D13 — Thu 08-06

- [ ] **Write:** Ch 1 *Introduction* (RQs and contributions — last, when you know what
      they are), Ch 15 *Conclusion*, Ch 16 *Future Work*, and the abstract.

## D14 — Fri 08-07 · buffer and polish

- [ ] Full read-through; every `\todo{}` resolved or deliberately left.
- [ ] `latexmk -C && latexmk -pdf thesis.tex`; zero undefined references.
- [ ] Title page: university, faculty, supervisors, submission date (`thesis.tex:107`)
      and the final title decision.
- [ ] Cross-check every claim in Ch 12 against a figure or table that exists.

## D15 — Sat 08-08 · submit

Buffer only. If you are writing new content today, the plan failed at an earlier gate —
ship what exists.

---

## Gate summary

| gate | date | question | if the answer is no |
|---|---|---|---|
| G1 | 07-25 | do seeds reproduce, and does `open62541 --optimal` connect? | fix before anything else; the protocol and 37 h of P0 depend on it |
| G2 | 07-26 | is the code frozen? | slip **one day at most**, pay for it out of P2 |
| G3 | 07-29 | is there a `sequence` result? | switch to narrative (c); the failure taxonomy becomes the thesis |
| G3b | 07-31 | does `open62541` reach the connect path? | the loitering result is the finding — write it as one, do not re-tune |
| G4 | 08-01 | are P0+P1 on track? | cut per 05-risks-and-cuts.md; do not eat writing days |
| G5 | 08-05 | are experiments frozen? | stop regardless; unanalysed runs are worth nothing |
