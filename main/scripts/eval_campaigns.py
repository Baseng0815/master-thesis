"""Campaign discovery and per-run metadata.

The evaluation data is a tree of per-run SQLite databases produced by the probe
suite in ``mugiwara/src/experiments/``.  Every run writes its own database, and
all three corpus-level targets share one schema (18 tables), so a single
target-agnostic reader covers that whole campaign.  What differs per target is
only the name of the ``action_rate`` series -- ``json_bytes`` / ``xml_bytes`` /
``http_bytes`` -- which this module normalises to the abstract "structural byte
rate" that the figures use.

The three input-level targets are the exception in both respects.  Each is a
single run rather than a multi-seed campaign, its database sitting directly in
the campaign root, and they carry fewer probes than the corpus runs and not the
same ones as each other: high-and-low has ``action_rate`` but no
``collapse_entropy``, sequence and open62541 the reverse, sequence alone has the
``action_tree_*`` tables, and none of the three has ``run_union``, so none of
them yields a coverage curve.  Extractors are failure-isolated for exactly this
reason and skip a probe their run does not carry.

Run metadata is read from the ``experiments`` table rather than from the
directory layout, because the layouts disagree: the cjson campaign has an
``evaluation.json`` per run plus a ``ledger.jsonl``, while the libxml2 and
picohttpparser campaigns have only a ``waves.log`` and a ``launch.sh``.  The
``experiments`` row is the one source present in every run, and it is
authoritative for the git revision, the seed and the resolved configuration.

File modification times are *not* metadata: the cjson directories are stamped
with the date they were rsynced off the training VM, not the date they ran.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path

# Default location of the consolidated experiment results.
DEFAULT_DATA_ROOT = Path("/home/bastian/mnt/experiment-results")

# Every campaign, in the order the results chapter reports it.  The value is
# the campaign root relative to the data root, or -- for a campaign that is a
# single run -- that run's database, which is how open62541 landed.
CAMPAIGNS: dict[str, str] = {
    "high-and-low": "high-and-low",
    "sequence": "sequence",
    "open62541": "open62541-thesis.db",
    "cjson": "runs/cjson",
    "libxml2": "libxml2-400",
    "picohttpparser": "picohttpparser-400",
}

# The input-level action-space campaigns are one run each rather than a tree of
# LABEL-sNN run directories: they are feasibility checks that were stopped once
# the target was solved, not multi-seed campaigns, so their database sits
# directly in the campaign root -- or, for open62541, is the campaign root, the
# data root holding other databases besides it.  Their arm label is fixed to
# MAIN, since there is nothing for it to distinguish.
SINGLE_RUN_CAMPAIGNS = frozenset({"high-and-low", "sequence", "open62541"})
SINGLE_RUN_LABEL = "MAIN"

# Directories under a campaign root that are not runs.
NON_RUN_DIRS = re.compile(r"^(_|discarded-)")

# A run directory is LABEL-sNN.  The label may itself contain digits and
# hyphens (CTRL-RAND, LIBXML2-400), so anchor on the seed suffix.
RUN_DIR = re.compile(r"^(?P<label>.+)-s(?P<seed>\d+)$")

# `status` is set by the experiment writer when the learner drops its hooks, so
# a run whose process died before that flush stays marked `running` forever.
# Six runs in the cjson campaign are affected: the T25 and SIMS100 arms lost
# between one and eight of their two hundred iterations, and T25-s03 never got
# its status updated at all even though the campaign ledger records it as
# completed with a full 21-hour duration.
#
# Discarding those would drop a seed from the best-performing arm over a
# bookkeeping artefact, so completeness is judged on the data instead: a run is
# kept when it reached most of the iterations its campaign ran for. What it
# actually reached is carried on the Run and reported in the inventory table,
# and the extractors align ragged runs by truncating to the shortest rather
# than padding, so a short run shortens a curve instead of inventing data.
MIN_ITERATION_FRACTION = 0.5

# Fields pulled out of the Rust `LearnerConfig` Debug string in
# `config_json.config_debug`.  Newer binaries also export some of these as
# proper JSON keys; the JSON value wins when both are present.
_DEBUG_FIELDS = {
    "root_dirichlet_alpha": float,
    "root_exploration_fraction": float,
    "num_iterations": int,  # MCTS simulations per move
    "training_iterations": int,
    "batch_size": int,
    "rollout_depth": int,
    "td_steps": int,
    "learning_rate": float,
    "replay_buffer_capacity": int,
    "reanalyze_ratio": float,
    "absorbing_depth": int,
}


@dataclass(frozen=True)
class Run:
    """One training run: its database and the metadata needed to label it."""

    target: str
    run_id: str
    label: str
    seed: int
    db: Path
    exp_id: str
    git_sha: str
    status: str
    iterations: int
    structural_series: str
    config: dict = field(default_factory=dict, repr=False)
    campaign_iterations: int = 0

    @property
    def is_control(self) -> bool:
        """True for the structure-blind random control arm (cjson only)."""
        return self.label == "CTRL-RAND"

    @property
    def is_complete(self) -> bool:
        """True when the run reached the full iteration count of its campaign."""
        return self.iterations >= self.campaign_iterations > 0

    @property
    def temperature(self) -> float | None:
        """The self-play temperature, or None when it is not constant.

        `temperature_samples` is the schedule evaluated at four points across
        training; the schedule itself is an opaque function pointer in the
        Debug string and cannot be read from there.
        """
        samples = self.config.get("temperature_samples")
        if not samples:
            return None
        return samples[0] if len(set(samples)) == 1 else None

    @property
    def slug(self) -> str:
        """Filesystem- and LaTeX-safe identifier."""
        return f"{self.target}-{self.run_id}".lower().replace("_", "-")


def _connect(db: Path) -> sqlite3.Connection:
    """Opens a run database strictly read-only.

    `immutable=1` promises sqlite the file will not change, which skips locking
    and the WAL entirely -- these databases are finished artefacts, and several
    still have a stale `-shm` file next to them from the training VM.
    """
    return sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)


def _parse_config(config_json: str) -> dict:
    """Flattens the stored configuration into one dict.

    The row holds a JSON object whose `config_debug` member is the Rust Debug
    rendering of `LearnerConfig`.  Everything outside that member is already
    structured and is kept verbatim; the fields listed in `_DEBUG_FIELDS` are
    recovered from the Debug string by regex, which is unlovely but is the only
    access to the search and optimiser settings.
    """
    raw = json.loads(config_json)
    debug = raw.pop("config_debug", "")
    parsed = dict(raw)
    for name, cast in _DEBUG_FIELDS.items():
        if name in parsed:
            continue  # the JSON key is authoritative when the binary exports it
        match = re.search(rf"\b{name}: ([^,}}]+)", debug)
        if not match:
            continue
        try:
            parsed[name] = cast(match.group(1).strip())
        except ValueError:
            parsed[name] = match.group(1).strip()
    return parsed


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _structural_series(con: sqlite3.Connection) -> str:
    """The name of this target's action-rate series, if it has one.

    One series per target (`json_bytes`, `xml_bytes`, `http_bytes`), measuring
    how often self-play plays an action from the target's grammar-relevant byte
    set.  Its value at iteration 0 is the measured chance rate and serves as
    the within-run control.  The high-and-low target carries the same probe
    under the name `high_coverage`, measuring how often self-play plays a byte
    that takes the high-coverage branch; the sequence and open62541 targets have
    no such probe and this is empty for them.
    """
    if not _has_table(con, "action_rate"):
        return ""
    row = con.execute("SELECT series FROM action_rate LIMIT 1").fetchone()
    return row[0] if row else ""


def _iteration_count(con: sqlite3.Connection) -> int:
    """How many learner iterations the run reached.

    `action_rate` is the per-iteration probe present in every corpus-action
    run, and it stays the source of record for them so this number cannot move
    under the published campaigns.  The sequence and open62541 targets do not
    carry that probe, so `buffer_state` -- the one per-iteration probe common to
    every schema in the campaign -- is the fallback.
    """
    for table in ("action_rate", "buffer_state"):
        if not _has_table(con, table):
            continue
        row = con.execute(f"SELECT MAX(iteration) + 1 FROM {table}").fetchone()
        if row and row[0] is not None:
            return int(row[0])
    return 0


def read_run(target: str, run_dir: Path) -> Run | None:
    """Reads one run directory, or returns None when it holds no usable run."""
    match = RUN_DIR.match(run_dir.name)
    if not match:
        return None
    databases = sorted(run_dir.glob("*-experiments.db"))
    if len(databases) != 1:
        return None
    return _read_database(target, run_dir.name, match.group("label"), int(match.group("seed")), databases[0])


def read_single_run(target: str, root: Path) -> Run | None:
    """Reads a campaign that is one run, its database sitting in the root.

    The run is identified by the stem of that database rather than by a
    directory name, because there is no run directory to carry a label and a
    seed; the seed comes from the `experiments` row, as it does everywhere.

    `root` may be the database itself rather than a directory holding it, which
    is what open62541 needs: its database sits at the data root next to the
    other campaigns' and next to an aborted partial run, so the campaign has to
    name the file it means.
    """
    databases = [root] if root.is_file() else sorted(root.glob("*.db"))
    if len(databases) != 1:
        return None
    return _read_database(target, databases[0].stem, SINGLE_RUN_LABEL, 0, databases[0])


def _read_database(target: str, run_id: str, label: str, seed_hint: int, db: Path) -> Run | None:
    """Reads the metadata of one run database."""
    with _connect(db) as con:
        row = con.execute(
            "SELECT id, git_sha, seed, status FROM experiments ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        exp_id, git_sha, db_seed, status = row
        config = _parse_config(
            con.execute("SELECT config_json FROM experiments WHERE id = ?", (exp_id,)).fetchone()[0]
        )
        structural = _structural_series(con)
        iterations = _iteration_count(con)

    return Run(
        target=target,
        run_id=run_id,
        label=label,
        seed=int(db_seed) if db_seed is not None else seed_hint,
        db=db,
        exp_id=exp_id,
        git_sha=git_sha or "",
        status=status,
        iterations=iterations,
        structural_series=structural,
        config=config,
    )


def discover(data_root: Path = DEFAULT_DATA_ROOT, targets: list[str] | None = None) -> list[Run]:
    """Finds every usable run across the configured campaigns.

    Skips the aborted development database at the data root (it sits outside a
    run directory and has a NULL seed), the `discarded-*` campaign whose runs
    were stopped early on purpose, and the `_waveN-binaries` directories, none
    of which are runs.

    The nominal length of a campaign is taken to be the longest run in it, and
    runs that fell far short of that are dropped as aborted; see
    `MIN_ITERATION_FRACTION`.
    """
    found: list[Run] = []
    for target, relative in CAMPAIGNS.items():
        if targets and target not in targets:
            continue
        root = data_root / relative
        if not root.exists():
            continue
        if target in SINGLE_RUN_CAMPAIGNS:
            run = read_single_run(target, root)
            if run is not None:
                found.append(run)
            continue
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or NON_RUN_DIRS.match(entry.name):
                continue
            run = read_run(target, entry)
            if run is not None:
                found.append(run)

    nominal: dict[str, int] = {}
    for run in found:
        nominal[run.target] = max(nominal.get(run.target, 0), run.iterations)
    return [
        replace(run, campaign_iterations=nominal[run.target])
        for run in found
        if run.iterations >= MIN_ITERATION_FRACTION * nominal[run.target]
    ]


def group_by_label(runs: list[Run]) -> dict[tuple[str, str], list[Run]]:
    """Groups runs into arms, keyed by (target, label), seeds ascending."""
    arms: dict[tuple[str, str], list[Run]] = {}
    for run in runs:
        arms.setdefault((run.target, run.label), []).append(run)
    for seeds in arms.values():
        seeds.sort(key=lambda r: r.seed)
    return arms
