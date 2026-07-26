# Frozen configuration

Fill this at **Gate G2 (2026-07-26, 23:59)** and never edit it afterwards. It is the
source for Appendix A (`app:configuration`) and for every "we used X" sentence in the
thesis.

## Provenance

- `~/efficientzero` commit: `<SHA>`
- `~/mugiwara` commit: `<SHA>`
- `~/fuzzyemu` commit: `<SHA>`
- freeze tag: `freeze-2026-07-26`
- frozen after development on: `sequence`
- transferred unchanged to: `branches`, `cjson`

## Values

Record the *effective* value (library default, or the example's override), and the
justification tier for each: **derived** > **empirically validated** > **inherited**.

| parameter | value | tier | justification |
|---|---|---|---|
| `learning_rate` | | empirical | 2e-2 destabilized training via NaN PER priorities (run 019f67bc); sweep shows a stable basin |
| `value_support` / `value_prefix_support` | `sequence_support()` | **derived** | the ±1 step-reward gap must span more than one bin or the value/value-prefix heads go action-blind — show the arithmetic |
| `num_iterations` (MCTS sims) | | empirical | 150 failed to replicate at −27 % throughput (07-12 campaign) |
| `batch_size` | | inherited | |
| `rollout_depth` | | inherited | |
| `td_steps` | | inherited | |
| `consistency_loss_coeff` | | inherited | ablated to 0.0 in `S-CONS0` |
| `value_prefix_loss_coeff` | | inherited | ablated to 0.0 in `S-VP0` |
| `policy_loss_coeff` | | inherited | 0.25 tried in the 07-12 campaign, mechanistically harmful |
| `value_loss_coeff` | | inherited | |
| `absorbing_state_supervision` / `absorbing_depth` | | empirical | tied to the dead-branch failure mode |
| `reanalyze_ratio` | | inherited | deviates from the reference 0.99 |
| `reanalyze_noise` | | empirical | `false` has collapsed training before |
| `model_size` | | inherited | |
| `replay_buffer_capacity` | | inherited | |
| `transitions_per_iteration` | | inherited | |
| `root_exploration_fraction` / `root_dirichlet_alpha` | | inherited | |
| `per_reward_coeff` / `per_alpha` / `per_beta` | | inherited | |
| run length bound | | — | added at infra §2; record the value used |

## Target-specific overrides

| target | override | why |
|---|---|---|
| `sequence` | `TERMINAL_COVERAGE_SCALE`, `NOVELTY_BONUS_SCALE`, `MAX_BLOCK_COUNT = 4096`, `value_support()` | reward shaping — declare it as shaping in `sec:targets-microbenchmarks` |
| `open62541` | `LIVING_REWARD = 1.0`, `CONNECTED_REWARD = 10.0`, `MAX_EPISODE_STEPS = 12`, `MAX_BLOCK_COUNT = 16384`, `DiscretizeSupport::new(-2.0, 4.5, 261)` | support is **derived** (returns to ~22 → h(22) ≈ 3.8 at ~0.025-h bin density keeps the +1 gap separable; see `open62541.rs:374-380`). Record the loiter-vs-connect margin (12 vs 14) as a *stated design property*, not an accident |
| `high_and_low` | | |
| `branches` | | |
| `cjson` | | raw coverage, no shaping — this is the point |
