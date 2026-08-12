"""Stage 1: per-run SQLite databases -> a compact CSV cache.

The campaign is ~133 GB of SQLite across 68 runs, with single tables reaching
13 M rows, so nothing downstream may query the databases directly: a figure
tweak would cost minutes.  This stage reads each database exactly once and
writes a few hundred kilobytes of CSV per run, which `eval_figures.py` then
reads in its entirety.

Every extractor is independent and failure-isolated.  That matters because the
schema drifts across the campaign: the wave-1 cjson runs (BASE, CTRL-RAND,
NOCOV, REUSE4, SIMS50, SIMS100, T15, T25, W0) predate the `episode_best` probe
and have 17 tables where the later runs have 18.  A missing table degrades that
one CSV, not the run.

Aggregation happens in SQL wherever a table is large, both because sqlite is
faster at it and because the aggregate is what the figure needs -- the raw
13 M-row introspection tables never enter Python.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import statistics
import time
import traceback
from collections import defaultdict
from pathlib import Path

from eval_campaigns import Run, _connect

# Time axes shared by every table.  `iteration` is populated only by the probes
# that run once per learner iteration (action_rate, collapse_entropy,
# buffer_state, policy_improvement); the rest carry env_steps and wall_ms only,
# so env_steps is the universal axis and iteration is derived by binning.
QUANTILE_HEADER = ["min", "q25", "median", "q75", "max", "mean"]

# Series kept from the two batch-diagnostic tables.  Both have a dozen series
# and over a million rows; these are the ones the figures use.
SAMPLED_SERIES = [
    "action_entropy",
    "rewarded_position_share",
    "rewarded_root_share",
    "reward_prefix_mean",
    "is_weight_mean",
    "bootstrap_share",
    "masked_share",
]
REANALYZED_SERIES = [
    "policy_entropy_root",
    "policy_entropy_mean",
    "policy_taken_mass_mean",
    "value_target_root_mean",
    "value_target_mean",
    "value_error_root_mean",
    "rewarded_target_share",
    "priority_mean",
]
BUFFER_SERIES = [
    "trajectories",
    "steps",
    "reward_total",
    "reward_max",
    "rewarded_step_share",
    "rewarded_priority_share",
    "priority_mean",
    "priority_p50",
    "priority_p90",
    "priority_p99",
]
IMPROVEMENT_SERIES = [
    "selfplay_kl_mean",
    "selfplay_prior_entropy",
    "selfplay_posterior_entropy",
    "selfplay_argmax_change_rate",
    "reanalyze_kl_mean",
    "reanalyze_prior_entropy",
    "reanalyze_posterior_entropy",
    "reanalyze_argmax_change_rate",
]

# Number of points kept on axes that are far denser than any figure needs.
LOSS_BINS = 400
TREE_BINS = 120

# Best inputs recorded per run for the qualitative table.
BEST_INPUT_COUNT = 10


def write_csv(path: Path, header: list[str], rows) -> int:
    """Writes rows to `path`, returning the number written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def summarise(values: list[float]) -> list[float]:
    """min / q25 / median / q75 / max / mean of a non-empty sample.

    Quantiles rather than mean and standard deviation throughout: the cjson
    outcome distribution is not Gaussian, and a mean lands in a valley where no
    run lives.
    """
    ordered = sorted(values)
    n = len(ordered)

    def at(fraction: float) -> float:
        return ordered[min(n - 1, max(0, int(round(fraction * (n - 1)))))]

    return [ordered[0], at(0.25), at(0.5), at(0.75), ordered[-1], statistics.fmean(ordered)]


# --------------------------------------------------------------------------
# Extractors.  Each takes (run, connection, output directory) and writes one
# CSV.  The name of the function after `x_` is the name of the CSV.
# --------------------------------------------------------------------------


def x_coverage(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """Union coverage and cumulative executions, aggregated over environments.

    `run_union` holds, per environment, the coverage that environment has ever
    reached and the executions it has spent, sampled once per learner
    iteration.  The environments write at interleaved `env_steps`, so grouping
    by `env_steps` yields one environment per group and is useless; the
    environments are instead aligned on their sample index, which is the
    iteration they were written at.

    Emits the coverage distribution across environments at each index, plus the
    three x-axes the results chapter needs: executions (the fuzzing currency),
    env_steps (the RL currency) and wall_ms (the wall-clock currency).
    """
    scores: dict[int, list[tuple[int, int, float]]] = defaultdict(list)
    executions: dict[int, list[tuple[int, int, float]]] = defaultdict(list)
    for series, env_steps, wall_ms, value in con.execute(
        "SELECT series, env_steps, wall_ms, value FROM run_union ORDER BY series, env_steps"
    ):
        kind, _, index = series.partition(".env")
        target = scores if kind == "score" else executions if kind == "executions" else None
        if target is not None:
            target[int(index)].append((env_steps, wall_ms, value))

    if not scores:
        return 0
    # Truncate to the shortest environment: a run killed mid-iteration can
    # leave one environment a sample short, and padding it would invent data.
    length = min(len(samples) for samples in scores.values())

    rows = []
    for i in range(length):
        coverage = [scores[env][i][2] for env in scores]
        execs = [executions[env][i][2] for env in executions] if executions else [0.0]
        env_steps = [scores[env][i][0] for env in scores]
        wall_ms = [scores[env][i][1] for env in scores]
        rows.append(
            [
                i,
                round(statistics.fmean(env_steps)),
                round(statistics.fmean(wall_ms)),
                round(statistics.fmean(execs), 2),
                round(sum(execs)),
                *[round(v, 3) for v in summarise(coverage)],
            ]
        )
    header = [
        "index",
        "env_steps",
        "wall_ms",
        "executions_per_env",
        "executions_total",
        *[f"cov_{name}" for name in QUANTILE_HEADER],
    ]
    return write_csv(out / "coverage.csv", header, rows)


def x_structural(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """Rate at which self-play plays a byte from the target's grammar.

    One series per target -- `json_bytes`, `xml_bytes`, `http_bytes` -- written
    once per learner iteration.  The value at iteration 0 is the untrained
    rate, which is the measured chance level and the within-run control this
    metric is read against.
    """
    rows = [
        [iteration, round(value, 5)]
        for iteration, value in con.execute(
            "SELECT iteration, value FROM action_rate WHERE series = ? ORDER BY iteration",
            (run.structural_series,),
        )
    ]
    return write_csv(out / "structural.csv", ["iteration", "rate"], rows)


def x_return(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """Per-trajectory return, binned into iterations.

    The table holds one row per finished trajectory -- 128 per iteration -- and
    carries no iteration column, so trajectories are chunked in `env_steps`
    order.  The result is the reward curve, as a distribution rather than a
    mean.
    """
    values = [
        (env_steps, wall_ms, value)
        for env_steps, wall_ms, value in con.execute(
            "SELECT env_steps, wall_ms, value FROM trajectory WHERE series = 'return' ORDER BY env_steps"
        )
    ]
    if not values or run.iterations == 0:
        return 0
    per_bin = max(1, len(values) // run.iterations)

    rows = []
    for iteration in range(run.iterations):
        chunk = values[iteration * per_bin : (iteration + 1) * per_bin]
        if not chunk:
            break
        rows.append(
            [
                iteration,
                chunk[-1][0],
                chunk[-1][1],
                *[round(v, 4) for v in summarise([v for _, _, v in chunk])],
            ]
        )
    header = ["iteration", "env_steps", "wall_ms", *[f"return_{n}" for n in QUANTILE_HEADER]]
    return write_csv(out / "return.csv", header, rows)


def x_loss(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """The five training losses, binned over training batches.

    Half a million rows per run at one row per batch per series; the figure
    needs a few hundred points, so sqlite bins them and reports the mean and
    the envelope within each bin.  The envelope is kept because the value loss
    spikes are themselves a finding.
    """
    maximum = con.execute("SELECT MAX(train_batches) FROM loss").fetchone()[0]
    if not maximum:
        return 0
    binned: dict[int, dict[str, tuple[float, float, float, float]]] = defaultdict(dict)
    for series, bin_index, batches, mean, low, high in con.execute(
        """
        SELECT series,
               train_batches * ? / (? + 1) AS bin,
               AVG(train_batches), AVG(value), MIN(value), MAX(value)
        FROM loss GROUP BY series, bin ORDER BY bin
        """,
        (LOSS_BINS, maximum),
    ):
        binned[bin_index][series] = (batches, mean, low, high)

    names = sorted({series for row in binned.values() for series in row})
    header = ["train_batches"] + [
        f"{series}_{suffix}" for series in names for suffix in ("mean", "min", "max")
    ]
    rows = []
    for bin_index in sorted(binned):
        row = binned[bin_index]
        batches = next(iter(row.values()))[0]
        cells: list = [round(batches)]
        for series in names:
            entry = row.get(series)
            cells += ["", "", ""] if entry is None else [round(v, 5) for v in entry[1:]]
        rows.append(cells)
    return write_csv(out / "loss.csv", header, rows)


def _pivot_by_iteration(
    con: sqlite3.Connection, table: str, series: list[str], out: Path, name: str
) -> int:
    """Pivots a small per-iteration table into one column per series."""
    values: dict[int, dict[str, float]] = defaultdict(dict)
    placeholders = ",".join("?" * len(series))
    for iteration, key, value in con.execute(
        f"SELECT iteration, series, value FROM {table} WHERE series IN ({placeholders})",
        series,
    ):
        values[iteration][key] = value
    rows = [
        [iteration] + [round(values[iteration].get(key, float("nan")), 6) for key in series]
        for iteration in sorted(values)
    ]
    return write_csv(out / f"{name}.csv", ["iteration", *series], rows)


def x_improvement(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """What search contributes over the raw policy prior.

    The divergence between the MCTS visit distribution and the network prior at
    the root, for self-play and for reanalyse.  This is the series that decides
    whether planning does anything or whether search only echoes the prior; no
    claim about planning is supportable without it.
    """
    return _pivot_by_iteration(con, "policy_improvement", IMPROVEMENT_SERIES, out, "improvement")


def x_buffer(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """Replay-buffer occupancy, reward density and priority distribution."""
    return _pivot_by_iteration(con, "buffer_state", BUFFER_SERIES, out, "buffer")


def _binned_series(
    con: sqlite3.Connection, table: str, series: list[str], bins: int, out: Path, name: str
) -> int:
    """Bins a large env_steps-indexed table into `bins` iteration-sized groups.

    `sampled_batch` and `reanalyzed_batch` carry no iteration column and hold
    over a million rows each, so they are aggregated in sqlite against a bin
    index derived from env_steps.
    """
    maximum = con.execute(f"SELECT MAX(env_steps) FROM {table}").fetchone()[0]
    if not maximum or bins == 0:
        return 0
    placeholders = ",".join("?" * len(series))
    binned: dict[int, dict[str, float]] = defaultdict(dict)
    steps: dict[int, float] = {}
    for key, bin_index, env_steps, mean in con.execute(
        f"""
        SELECT series, env_steps * ? / (? + 1) AS bin, AVG(env_steps), AVG(value)
        FROM {table} WHERE series IN ({placeholders}) GROUP BY series, bin
        """,
        (bins, maximum, *series),
    ):
        binned[bin_index][key] = mean
        steps[bin_index] = env_steps
    rows = [
        [index, round(steps[index])]
        + [round(binned[index].get(key, float("nan")), 6) for key in series]
        for index in sorted(binned)
    ]
    return write_csv(out / f"{name}.csv", ["iteration", "env_steps", *series], rows)


def x_sampled(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """Composition of the batches actually trained on."""
    return _binned_series(con, "sampled_batch", SAMPLED_SERIES, run.iterations, out, "sampled")


def x_reanalyzed(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """Freshly searched policy and value targets, for calibration."""
    return _binned_series(
        con, "reanalyzed_batch", REANALYZED_SERIES, run.iterations, out, "reanalyzed"
    )


def x_collapse(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """MCTS visit-count entropy per episode-step position, over training.

    A position × iteration matrix, which is the natural form for the collapse
    heatmap: entropy falling to near zero at every position is the signature of
    a policy that has stopped exploring.
    """
    rows = []
    for iteration, series, value in con.execute(
        "SELECT iteration, series, value FROM collapse_entropy ORDER BY iteration"
    ):
        if not series.startswith("visit_entropy_p"):
            continue
        rows.append([iteration, int(series.removeprefix("visit_entropy_p")), round(value, 5)])
    rows.sort(key=lambda row: (row[0], row[1]))
    return write_csv(out / "collapse.csv", ["iteration", "position", "entropy"], rows)


def x_depth_actions(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """The most-played action at each position, and the mass it holds.

    Millions of (iteration, position, action) counts reduce to one row per
    (iteration, position): which action dominates and what share of plays it
    takes.  A share approaching one is the policy-collapse matrix.
    """
    rows = [
        [iteration, position, action, count, total, round(count / total, 5) if total else 0.0]
        for iteration, position, action, count, total in con.execute(
            """
            SELECT iteration, position, action, cnt, total FROM (
              SELECT iteration, position, action, count AS cnt,
                     SUM(count) OVER (PARTITION BY iteration, position) AS total,
                     ROW_NUMBER() OVER (
                         PARTITION BY iteration, position ORDER BY count DESC, action
                     ) AS rn
              FROM depth_action_counts)
            WHERE rn = 1 ORDER BY iteration, position
            """
        )
    ]
    header = ["iteration", "position", "top_action", "top_count", "total", "top_share"]
    return write_csv(out / "depth_actions.csv", header, rows)


def x_tree(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """Growth of the action-execution trie, by depth and over time.

    `action_tree_nodes` records each distinct action prefix the run ever
    executed, with the env_steps at which it was first reached.  Counting nodes
    per depth over time separates a run that searches deep and narrow from one
    that searches broad and shallow -- the distinction the head-to-head
    comparison rests on.
    """
    maximum = con.execute("SELECT MAX(first_env_steps) FROM action_tree_nodes").fetchone()[0]
    if not maximum:
        return 0
    rows = [
        [bin_index, round(env_steps), depth, nodes]
        for bin_index, env_steps, depth, nodes in con.execute(
            """
            SELECT first_env_steps * ? / (? + 1) AS bin, AVG(first_env_steps), depth, COUNT(*)
            FROM action_tree_nodes GROUP BY bin, depth ORDER BY bin, depth
            """,
            (TREE_BINS, maximum),
        )
    ]
    return write_csv(out / "tree.csv", ["bin", "env_steps", "depth", "new_nodes"], rows)


def x_introspect(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """Open-loop unroll of the learned model, per latent depth.

    After each iteration the model is unrolled along a fixed action path purely
    in latent space.  Per (iteration, level) this keeps the action the policy
    head ranks first and the mass it gives it, the entropy of the head, and the
    value it predicts -- the evidence for whether the model ranks the right
    action at depth and holds it.
    """
    entropy = {
        (iteration, level): value
        for iteration, level, value in con.execute(
            """
            SELECT iteration, level, SUM(-prob * ln(MAX(prob, 1e-12)))
            FROM introspect_policy GROUP BY iteration, level
            """
        )
    }
    values = {
        (iteration, level): (mean, high)
        for iteration, level, mean, high in con.execute(
            "SELECT iteration, level, AVG(value), MAX(value) FROM introspect_value GROUP BY iteration, level"
        )
    }
    rows = []
    for iteration, level, action, prob in con.execute(
        """
        SELECT iteration, level, action, prob FROM (
          SELECT iteration, level, action, prob,
                 ROW_NUMBER() OVER (
                     PARTITION BY iteration, level ORDER BY prob DESC, action
                 ) AS rn
          FROM introspect_policy)
        WHERE rn = 1 ORDER BY iteration, level
        """
    ):
        mean, high = values.get((iteration, level), (float("nan"), float("nan")))
        rows.append(
            [
                iteration,
                level,
                action,
                round(prob, 6),
                round(entropy.get((iteration, level), float("nan")), 5),
                round(mean, 5),
                round(high, 5),
            ]
        )
    header = ["iteration", "level", "top_action", "top_prob", "entropy", "value_mean", "value_max"]
    return write_csv(out / "introspect.csv", header, rows)


def x_best_inputs(run: Run, con: sqlite3.Connection, out: Path) -> int:
    """The highest-coverage inputs the run produced, for the qualitative table.

    Prefers `episode_best`, which the environment records directly; falls back
    to `seed`, which recovers inputs from stored observations.  The wave-1
    cjson runs predate `episode_best` and take the fallback, and the NOSEED arm
    zeroes the seed bytes in the observation, so on that arm the fallback would
    report nothing meaningful -- which is why the source is recorded per row.
    """
    tables = {name for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "episode_best" in tables:
        query = """
            SELECT block_score, executions, seed_ascii, seed_hex
            FROM episode_best ORDER BY block_score DESC, executions ASC LIMIT ?
        """
        source = "episode_best"
    else:
        query = """
            SELECT coverage_score, env_steps, seed_ascii, seed_hex
            FROM seed ORDER BY coverage_score DESC, env_steps ASC LIMIT ?
        """
        source = "seed"
    rows = [
        [rank, source, score, cost, ascii_text, hex_text[:512]]
        for rank, (score, cost, ascii_text, hex_text) in enumerate(con.execute(query, (BEST_INPUT_COUNT,)), 1)
    ]
    header = ["rank", "source", "coverage_score", "cost", "seed_ascii", "seed_hex"]
    return write_csv(out / "best_inputs.csv", header, rows)


EXTRACTORS = {
    "coverage": x_coverage,
    "structural": x_structural,
    "return": x_return,
    "loss": x_loss,
    "improvement": x_improvement,
    "buffer": x_buffer,
    "sampled": x_sampled,
    "reanalyzed": x_reanalyzed,
    "collapse": x_collapse,
    "depth_actions": x_depth_actions,
    "tree": x_tree,
    "introspect": x_introspect,
    "best_inputs": x_best_inputs,
}


def summarise_run(run: Run, out: Path) -> dict:
    """Derives the per-run scalars the summary figures and tables need.

    Read back from the CSVs this run just wrote rather than from the database,
    so the numbers quoted in the text are exactly the numbers plotted.
    """
    summary: dict = {
        "target": run.target,
        "run_id": run.run_id,
        "label": run.label,
        "seed": run.seed,
        "git_sha": run.git_sha[:12],
        "iterations": run.iterations,
        "temperature": run.temperature,
        "root_dirichlet_alpha": run.config.get("root_dirichlet_alpha"),
        "mcts_simulations": run.config.get("mcts_simulations") or run.config.get("num_iterations"),
        "model_size": run.config.get("model_size"),
        "block_count": run.config.get("block_count"),
        "structural_series": run.structural_series,
    }

    coverage = _read_csv(out / "coverage.csv")
    if coverage:
        first, last = coverage[0], coverage[-1]
        final = float(last["cov_median"])
        summary |= {
            "coverage_initial": float(first["cov_median"]),
            "coverage_final_median": final,
            "coverage_final_min": float(last["cov_min"]),
            "coverage_final_max": float(last["cov_max"]),
            "executions_per_env": float(last["executions_per_env"]),
            "executions_total": float(last["executions_total"]),
            "wall_hours": float(last["wall_ms"]) / 3.6e6,
            "env_steps": float(last["env_steps"]),
        }
        # Sample efficiency: executions to reach 90 % of the coverage this run
        # ended at.  Reported per environment, since that is the unit an
        # environment's execution budget is spent in.
        threshold = float(first["cov_median"]) + 0.9 * (final - float(first["cov_median"]))
        for row in coverage:
            if float(row["cov_median"]) >= threshold:
                summary["executions_to_90pct"] = float(row["executions_per_env"])
                summary["iteration_to_90pct"] = int(row["index"])
                break

    structural = _read_csv(out / "structural.csv")
    if structural:
        rates = [(int(row["iteration"]), float(row["rate"])) for row in structural]
        peak_iteration, peak = max(rates, key=lambda item: item[1])
        summary |= {
            "structural_chance": rates[0][1],
            "structural_peak": peak,
            "structural_peak_iteration": peak_iteration,
            "structural_final": rates[-1][1],
            "structural_decay": peak - rates[-1][1],
        }

    returns = _read_csv(out / "return.csv")
    if returns:
        summary["return_final_median"] = float(returns[-1]["return_median"])
        summary["return_max"] = max(float(row["return_max"]) for row in returns)

    best = _read_csv(out / "best_inputs.csv")
    if best:
        summary["best_input_score"] = float(best[0]["coverage_score"])
        summary["best_input_ascii"] = best[0]["seed_ascii"]
    return summary


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def extract_run(run: Run, cache: Path, only: list[str] | None, force: bool) -> dict:
    """Runs every extractor for one run and returns its summary."""
    out = cache / run.target / run.run_id
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {}
    started = time.monotonic()

    with _connect(run.db) as con:
        for name, extractor in EXTRACTORS.items():
            if only and name not in only:
                continue
            destination = out / f"{name}.csv"
            if destination.is_file() and not force:
                report[name] = "cached"
                continue
            try:
                report[name] = extractor(run, con, out)
            except sqlite3.Error as error:
                # Expected for the wave-1 runs, which lack `episode_best`.
                report[name] = f"error: {error}"
            except Exception:  # noqa: BLE001 - one bad extractor must not lose the run
                report[name] = f"error: {traceback.format_exc(limit=1).strip()}"

    summary = summarise_run(run, out)
    summary["extract_seconds"] = round(time.monotonic() - started, 1)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    summary["_report"] = report
    return summary
