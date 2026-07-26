# Infrastructure — the critical path (D1–D2)

Everything here is in `~/efficientzero` or `~/mugiwara`, not in the thesis repo.

Build reminder: no `cargo` outside the dev shell —
`nix develop -c cargo run --release --example sequence --features cuda -- <args>`.

## Status as of 2026-07-25

| item | state |
|---|---|
| §1 seed control | **landed** — `--seed`, substreams per `RngRole` |
| §2 run-length bound | **landed** — `--max-iterations` *or* `--max-wall-seconds`, plus graceful SIGTERM |
| §5 queue runner | **landed** — `mugiwara::evaluations`, `campaign` binary |
| §8 `sequence` example is stale | **NEW BLOCKER — read it first** |
| §3 eval-mode probe | open |
| §4 `high_and_low` instrumentation | open |
| §6 climber baseline | open |
| §7 `open62541` smoke test | open |

---

## §8 `examples/sequence.rs` does not compile — **BLOCKING, and new**

`cargo check --example sequence` fails with five errors. They are all staleness against
the emulator refactor to `mogi_quickstart`, not anything to do with the seed work:

- `mogi_fuzzer` and `mogi_unicorn` are imported but were removed from `Cargo.toml`,
- `mugiwara::{EmulatorArgs, MugiEmulator, build_emulator}` moved to `mugiwara::emulator`,
- `test_cases::sequence` no longer resolves,
- `mogi_emulator::…::x86::X86` moved.

`open62541`, `cjson` and `branches` were migrated; `sequence` was not.

**Why this outranks everything else:** `sequence` is the calibration target. The frozen
configuration is developed on it and then transferred unchanged
(`sec:methodology-hyperparameters`), 30 of P0's 51 runs are on it, and Gate G3 on D5 is
defined as "is there a `sequence` result". Until it builds, the campaign cannot start.

**Do:** port it the way `open62541.rs` was ported — construct the emulator through
`mogi_quickstart::emulator` against the staged `Case` — rather than reviving the deleted
`build_emulator` path.

## §1 Seed control end to end — **landed**

`--seed <u64>` on the learner CLI, splitting one master seed into per-role substreams
(`efficientzero/src/random`, `RngRole`). Two consequences for the campaign:

- A seed pins each stream's *content*, not the *order* concurrent workers consume it.
  Exact replay additionally needs `--data-worker-count 1 --rollout-worker-count 1
  --reanalyze-worker-count 1`, and GPU reduction order still leaves a residual.
- The campaign therefore does **not** pin workers on its 51 P0 runs: it only needs seeds
  recorded and distinct. `campaign replay` (two runs, one seed, single workers, 200
  iterations) is the Gate G1 check, and whatever residual it shows is what
  `sec:impl-reproducibility` should state.

### Still open here

- [ ] `git_sha` is still `None` in both instrumented examples, so runs do not record the
      commit they came from. Confirmatory claims (`sec:methodology-preregistration`) need
      it. Cheapest fix: have the campaign export it and the examples read it.

## §2 Run-length bound — **landed**

Two mutually exclusive flags, `--max-iterations <n>` and `--max-wall-seconds <s>`,
expressed in config as `RunLimit` so the bound is a *recorded property of the run*
rather than implied by how the process was launched.

Reaching either is a clean stop, not a kill: the learner leaves its loop the same way it
does on SIGINT, so the final model is written and every hook flushes. SIGINT/SIGTERM do
the same thing, and a second signal exits immediately.

The queue runner uses this: on its wall-clock safety net it sends SIGTERM and waits five
minutes before killing, so a timed-out run still saves its model. The ledger distinguishes
`timed_out` (stopped when asked) from `killed` (had to be forced) — treat a `killed`
run's database rows as suspect.

## §3 Eval-mode probe

**Why:** the highest-value metric gap. Solve depth is currently inferred from noisy
training returns; the headline learning curve should come from a greedy, noise-free
rollout.

**Do:**

- [ ] Every `K` learner iterations, run one evaluation episode with temperature 0 and
      root noise disabled (`MCTSConfig::without_exploration_noise` already exists at
      `mcts/mod.rs:176`).
- [ ] Log `solve.max_depth`, `solve.solved` (bool), and per-depth correct-action rate.
- [ ] `K` small enough for a smooth curve, large enough not to dominate cost — start
      at 10 (matching `model_checkpoint_interval`) and check the overhead in the D2 pilot.

**Accept:** an eval series in the DB whose max depth is monotone-ish and readable
without smoothing.

---

## §4 `high_and_low` instrumentation

**Why:** it has **no** `ExperimentWriter`, **no** probes and no DB — it logs a running
average and nothing else (263 lines). It cannot produce a thesis figure as it stands.

**Do:**

- [ ] Mirror the `sequence.rs` wiring: `ExperimentSpec` (db `./high-and-low-experiments.db`),
      `ExperimentWriter::spawn`, `with_experiments`.
- [ ] Probes: `LossProbe`, `ReturnProbe`, `BufferStateProbe`, plus the eval probe from §3.
- [ ] The target-appropriate headline metric is **rate of choosing a high-coverage
      byte**, not depth — a bandit has no depth. Log it per eval episode.
- [ ] `ModelIntrospectProbe` needs a fixed action path; for a bandit use the
      single-step action ranking instead.

**Accept:** a 30-minute run produces a learning curve you would put in the thesis.

---

## §5 Queue runner — **landed**

`mugiwara::evaluations`, driven by the `campaign` binary. The queue lives in Rust
(`evaluations::matrix`) rather than in text files, so a row is type-checked and the
matrix is itself the record of what was run.

```sh
nix develop -c cargo build --release --bin campaign
./target/release/campaign p0 --backend cuda --timeout-hours 4
./target/release/campaign p0 --dry-run      # print the argv of every run
```

Run the **built binary**, not `cargo run`: the campaign shells out to `cargo build` per
example, and a cargo-launched parent can hold the target-directory lock its child waits
on. `--dry-run` is safe either way.

Tiers: `replay` (Gate G1), `p0` (51 runs, ~88.5 h), `p1` (33, ~70.5 h), `p2` (29, ~61 h).

- **Resumable.** A ledger (`runs/<tier>/ledger.jsonl`) records every finished run;
  restarting skips completed ones and **retries failed ones** — a crashed run is still
  owed.
- **Self-describing.** Each run directory holds the serialised `Evaluation`, its log, its
  model and **its own experiment database** (`MW_DB`), so 2-wide running never contends
  on one SQLite writer and every result traces back to what produced it.
- **Failures do not stop the queue.** Only a failed build or an unwritable ledger aborts.

**Still open:** selecting a baseline *policy* is not a driver flag, so `S-RAND`/`S-CLIMB`
are not schedulable and P0 currently carries only the oracle control (§6).

---

## §6 Coverage-guided climber baseline — P0 for the argument

**Why:** `sec:methodology-baselines`. Uniform random against a 16-byte lock is a
strawman; an AFL-style climber walks such a lock byte by byte. Every claim of the form
"the model matters" is against *this*, not against random.

**Do:**

- [ ] Implement as a `Policy` in `~/mugiwara/src/policies/` next to
      `randomized.rs`: keep the current prefix while a candidate byte increases
      coverage, otherwise try the next; no network, no MCTS.
- [ ] Drive it through the same environment and the same probes so the curves are
      directly comparable — same x-axis, same coverage accounting.
- [ ] Runs are cheap (no training): budget ~20 min each.

**Does not touch the learner**, so it may land on D3 after the freeze.

**Accept:** a climber curve and a random curve on the same axes as the RL curve, all
three from the same probe code.

---

## §7 `open62541` smoke test and re-cost — do this **first on D1**

**Why:** 37 h of P0 runs on this target, and `findings/open62541-example.md` (07-13)
recorded that the `../fuzzing-test-cases` checkout had been trimmed to three cases and
that restoring `open62541` needs a submodule init plus a Docker build via `build.rs`.
That looks resolved — `~/fuzzing-test-cases/test-cases/` now lists all 14 cases
including `open62541`, and a built sysroot sits at
`~/fuzzing-test-cases-o62/built/open62541` — but "looks resolved" is not "verified", and
finding out on D6 costs the tier.

**Do:**

- [ ] `nix develop -c cargo run --example open62541 -- --evaluate model.mpk --optimal`
      and confirm the four-step trace still ends `activate_sess … connected=true`.
- [ ] Confirm the diagnostics land in `./open62541-experiments.db`.
- [ ] Time a short `--train` run and put a real number into the matrix's h/run column.
- [ ] Populate `ExperimentSpec.seed` / `git_sha` / `label` here too, not just in
      `sequence.rs`.

**Good news:** this example needs no probe work. It already carries the full set —
including `CollapseProbe::new(ACTION_COUNT)` at `open62541.rs:517`, which `sequence.rs`
is still missing — and a `ModelIntrospectProbe` along the connect path, which is exactly
the per-depth mechanism figure the results chapter needs.

**Also do (small, enables a P1 experiment):**

- [ ] Promote `CONNECTED_REWARD` (`open62541.rs:97`) to a CLI flag or env var. It is a
      constant today, so the `O-REW20` / `O-REW5` reward-margin experiment would
      otherwise need three separate binaries. Changing an example constant is not a
      learner change and does not violate the code freeze, but a flag keeps the value
      *recorded in `config_json`* rather than implied by which binary ran.

---

## Optional, only if D1–D2 finish early

- [ ] **Phase timing** (emulation / inference / training split) — needed for the
      wall-clock currency in `sec:methodology-currencies`. Cheap and high-value for the
      honesty argument; if it slips, report total wall-clock only and say so.
- [ ] **Policy-improvement metric** — KL between the MCTS visit-count policy and the
      network prior at the root. This is the direct evidence for the echo-chamber
      failure mode in Ch 13. Nice to have, not blocking.
- [ ] **Coverage-vs-executions curve** at run level — the standard fuzzing axis. Needed
      only if a raw-coverage target (`cjson`) makes it into the matrix; then it is not
      optional.
