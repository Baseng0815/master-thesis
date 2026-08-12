#!/usr/bin/env python3
"""Turns the fuzzing campaigns into the figures and tables of the thesis.

Two stages, because the campaign is ~133 GB of SQLite and re-querying it for
every plot tweak is not workable:

    evaluate.py extract     per-run databases -> CSV cache   (slow, run once)
    evaluate.py figures     CSV cache -> figures/data + figures/generated

`extract` is incremental: a run whose CSVs already exist is skipped unless
`--force` is given, so adding a campaign or fixing one extractor costs only the
work that changed.

Standard library only, deliberately. This script has to still run when the
thesis is opened again years from now, and it is the provenance of every number
in \\cref{chap:results}; a dependency on a scientific-Python stack that has
since moved on would make those numbers unreproducible. All of the heavy
aggregation happens in sqlite, which is better at it than Python would be.

Usage:
    ./scripts/evaluate.py runs                    # inventory, no extraction
    ./scripts/evaluate.py extract                 # fill the cache
    ./scripts/evaluate.py extract --target cjson --force
    ./scripts/evaluate.py figures                 # write figures + data
    ./scripts/evaluate.py figures --only saturation
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_campaigns  # noqa: E402
import eval_extract  # noqa: E402
import eval_figures  # noqa: E402

# The cache lives next to the data rather than in the thesis repository: it is
# derived, it is a few tens of megabytes, and it should not be committed.
DEFAULT_CACHE = eval_campaigns.DEFAULT_DATA_ROOT / "_evalcache"

THESIS_ROOT = Path(__file__).resolve().parent.parent


def cmd_runs(args: argparse.Namespace) -> int:
    runs = eval_campaigns.discover(args.data_root, args.target)
    if not runs:
        print(f"no finished runs under {args.data_root}", file=sys.stderr)
        return 1
    arms = eval_campaigns.group_by_label(runs)
    print(f"{len(runs)} runs in {len(arms)} arms\n")
    print(
        f"{'target':<15}{'arm':<21}{'seeds':<9}{'iterations':<13}"
        f"{'T':<7}{'alpha':<11}{'revision'}"
    )
    incomplete = []
    for (target, label), group in sorted(arms.items()):
        first = group[0]
        temperature = first.temperature
        lengths = {run.iterations for run in group}
        iterations = (
            str(first.campaign_iterations)
            if lengths == {first.campaign_iterations}
            else f"{min(lengths)}-{max(lengths)}/{first.campaign_iterations}"
        )
        print(
            f"{target:<15}{label:<21}"
            f"{','.join(str(run.seed) for run in group):<9}"
            f"{iterations:<13}"
            f"{(f'{temperature:g}' if temperature else 'sched'):<7}"
            f"{first.config.get('root_dirichlet_alpha', '?'):<11}"
            f"{first.git_sha[:7]}"
        )
        incomplete += [run for run in group if not run.is_complete or run.status != "finished"]

    if incomplete:
        print("\nincomplete runs (kept, but the arm is short of its nominal length):")
        for run in incomplete:
            print(
                f"  {run.target}/{run.run_id}: {run.iterations}/{run.campaign_iterations}"
                f" iterations, status={run.status}"
            )

    # An arm whose seeds ran on different binaries is not four samples of one
    # configuration, and nothing else in the layout says so.
    split = {
        key: group
        for key, group in arms.items()
        if len({run.git_sha for run in group}) > 1
    }
    if split:
        print("\narms whose seeds were built from different revisions:")
        for (target, label), group in sorted(split.items()):
            print(f"  {target}/{label}:")
            for run in group:
                print(f"    s{run.seed:02d}  {run.git_sha[:12]}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    runs = eval_campaigns.discover(args.data_root, args.target)
    if not runs:
        print(f"no finished runs under {args.data_root}", file=sys.stderr)
        return 1
    print(f"extracting {len(runs)} runs into {args.cache}")
    started = time.monotonic()
    failures = 0
    for index, run in enumerate(runs, 1):
        elapsed = time.monotonic() - started
        print(f"[{index:>3}/{len(runs)}] {run.target}/{run.run_id} ({elapsed / 60:.1f} min elapsed)", flush=True)
        summary = eval_extract.extract_run(run, args.cache, args.only, args.force)
        for name, outcome in summary["_report"].items():
            if isinstance(outcome, str) and outcome.startswith("error"):
                failures += 1
                print(f"         {name}: {outcome}", file=sys.stderr)
        print(f"         {summary['extract_seconds']}s", flush=True)
    print(f"done in {(time.monotonic() - started) / 60:.1f} min, {failures} extractor failures")
    return 0


def cmd_figures(args: argparse.Namespace) -> int:
    runs = eval_campaigns.discover(args.data_root, args.target)
    cached = [run for run in runs if (args.cache / run.target / run.run_id / "summary.json").is_file()]
    if not cached:
        print("cache is empty -- run `evaluate.py extract` first", file=sys.stderr)
        return 1
    if len(cached) < len(runs):
        print(f"warning: {len(runs) - len(cached)} runs are not in the cache and are omitted", file=sys.stderr)
    written = eval_figures.build(args.root, args.cache, cached, args.only)
    for path in written:
        print(path.relative_to(args.root))
    print(f"\n{len(written)} files written. \\input them from the results chapter, e.g.")
    print(r"  \input{figures/generated/coverage-executions}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-root", type=Path, default=eval_campaigns.DEFAULT_DATA_ROOT,
        help="root of the consolidated experiment results",
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="CSV cache directory")
    parser.add_argument(
        "--target", action="append", choices=list(eval_campaigns.CAMPAIGNS),
        help="restrict to one target (repeatable)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("runs", help="list the runs that would be evaluated").set_defaults(fn=cmd_runs)

    extract = sub.add_parser("extract", help="fill the CSV cache from the run databases")
    extract.add_argument("--force", action="store_true", help="re-extract runs already cached")
    extract.add_argument(
        "--only", action="append", choices=list(eval_extract.EXTRACTORS),
        help="run only these extractors (repeatable)",
    )
    extract.set_defaults(fn=cmd_extract)

    figures = sub.add_parser("figures", help="write figure data and stubs from the cache")
    figures.add_argument("--root", type=Path, default=THESIS_ROOT, help="thesis repository root")
    figures.add_argument(
        "--only", action="append", choices=list(eval_figures.FIGURES),
        help="build only these figures (repeatable)",
    )
    figures.set_defaults(fn=cmd_figures)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
