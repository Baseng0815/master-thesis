"""Stage 2: the CSV cache -> pgfplots data files and figure stubs.

Nothing here touches a database.  It reads the cache written by
`eval_extract.py` and writes two kinds of file:

  figures/data/*.csv        the plotted numbers, one file per figure
  figures/generated/*.tex   a float per figure, \\input from a results chapter

The figures are pgfplots rather than rendered images so that they use the
document's fonts and the template's KIT colours, and so that restyling one does
not mean re-running extraction.  Generated files are kept in their own
directory: everything in `figures/generated/` is disposable and is rewritten by
`evaluate.py figures`, while `figures/` proper holds the hand-drawn TikZ.

Conventions that hold across every figure:

  * Distributions are drawn as a median line inside a quantile band, never as a
    mean with a standard deviation.  The cjson outcome distribution is bimodal
    and a mean would land in a valley where no run lives.
  * Coverage is never shared across targets on one axis.  The three targets
    instrument different numbers of basic blocks (picohttpparser 4096, libxml2
    16384) and their coverage ranges differ by two orders of magnitude, so
    absolute coverage gets one panel per target and only normalised quantities
    are overlaid.
  * The structural-byte rate is always drawn against its own chance level, the
    untrained rate measured at iteration 0.  That is the within-run control the
    libxml2 and picohttpparser claims rest on, since those campaigns have no
    random-control arm.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

from eval_campaigns import Run, group_by_label

# Order the results chapter reports the targets in, with display names.
TARGETS = {
    "cjson": "cJSON",
    "libxml2": "libxml2",
    "picohttpparser": "picohttpparser",
}

# The input-level action-space targets, in the order the results chapter
# reports them.  These are feasibility checks rather than campaigns -- one run
# each, one seed -- so their figures share no emitter with the corpus targets:
# there is no seed spread to draw a band from, and no coverage probe to draw a
# coverage curve from.  What they do carry is the same return, loss and entropy
# instrumentation, which is what the section reports.
INPUT_TARGETS = {
    "high-and-low": "high-and-low",
    "sequence": "sequence",
}

# Size of each input-level target's action space.  Its logarithm is the entropy
# of the uniform policy, which is where an untrained agent starts and therefore
# the reference the entropy curves are read against.
INPUT_ACTION_SPACE = {"high-and-low": 256, "sequence": 26}

# The episode length that counts as solving the target, where the target has
# one.  On sequence it is the length of the passcode: the program exits on the
# first wrong byte, so a 16-step episode is a fully recovered passcode.  Taken
# from the target rather than from the highest length the run happened to
# reach, so that the reference line means what the caption says it means even
# if a run never gets there.
INPUT_EPISODE_CEILING = {"sequence": 16}

# The cjson arms that carry the head-to-head story, in plotting order.  The
# rest of the campaign appears only in the ablation figures.
CJSON_HEADLINE = ["T25", "ALPHA004", "BASE", "CTRL-RAND"]

# Human-readable ablation descriptions, keyed by arm label.  Taken from the
# `description` each run was launched with.
ARM_CAPTIONS = {
    "BASE": "frozen baseline",
    "CTRL-RAND": "structure-blind random mutation",
    "ALPHA004": r"root Dirichlet $\xi$ scaled to the action space",
    "ALPHA010": r"root Dirichlet $\xi = 0.1$",
    "EDGE": "edge- instead of block-coverage",
    "MEDIUM": "medium hidden-width preset",
    "NOCOV": "coverage zeroed in the observation",
    "NOSEED": "seed bytes zeroed in the observation",
    "REUSE4": r"$4\times$ sample reuse",
    "SIMS50": "50 MCTS simulations",
    "SIMS100": "100 MCTS simulations",
    "SMALL": "small hidden-width preset",
    "T15": r"constant temperature $T = 1.5$",
    "T25": r"constant temperature $T = 2.5$",
    "W0": "depth-record reward term disabled",
}

# The template's line styles, cycled in this order so a colour means the same
# arm in every figure of a group.
LINE_STYLES = ["KIT line plot A", "KIT line plot B", "KIT line plot C", "KIT line plot D", "KIT line plot E"]
BAND_FILLS = ["KITblue15", "KITred15", "KITorange15", "KITlilac15", "KITbrown15"]

DATA_DIR = Path("figures/data")
TEX_DIR = Path("figures/generated")


# --------------------------------------------------------------------------
# Cache access
# --------------------------------------------------------------------------


def load(cache: Path, run: Run, name: str) -> list[dict]:
    path = cache / run.target / run.run_id / f"{name}.csv"
    if not path.is_file():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def load_summary(cache: Path, run: Run) -> dict:
    import json

    path = cache / run.target / run.run_id / "summary.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def num(row: dict, key: str, default: float = float("nan")) -> float:
    value = row.get(key, "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pool_by_index(series: list[list[dict]], key: str, index: str = "index") -> dict[int, list[float]]:
    """Pools one column of several per-seed tables, keyed on the shared index.

    All seeds of an arm share a sampling grid (one sample per learner
    iteration), so pooling on the index is exact and needs no interpolation.
    """
    pooled: dict[int, list[float]] = defaultdict(list)
    for rows in series:
        for row in rows:
            value = num(row, key)
            if value == value:  # not NaN
                pooled[int(float(row[index]))].append(value)
    return pooled


def shared_ylabel(text: str, first: bool) -> str:
    """Labels the ordinate, on the leftmost panel only in the side-by-side form.

    Three panels in a row each carrying their own rotated axis label spend
    about a third of the text block on label text, which does not fit; since
    the panels of a figure always show the same quantity, the name goes on the
    left-hand one and the others keep only their tick labels. Stacked panels
    each have a row to themselves and compete for no width, so they are all
    labelled.
    """
    return f"ylabel={{{text}}}" if first or PANEL_LAYOUT == "column" else "ylabel={}"


def _count_word(count: int) -> str:
    """Spells a small count, so captions read correctly when a target is absent.

    Captions state how many targets a claim rests on, and a partially extracted
    cache would otherwise silently produce a caption that overstates it.
    """
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(count, str(count))


def quantiles(values: list[float]) -> tuple[float, float, float]:
    """Low / median / high across seeds, as the 25th, 50th and 75th percentile."""
    ordered = sorted(values)
    n = len(ordered)

    def at(fraction: float) -> float:
        return ordered[min(n - 1, max(0, int(round(fraction * (n - 1)))))]

    return at(0.25), at(0.5), at(0.75)


# --------------------------------------------------------------------------
# Emitters
# --------------------------------------------------------------------------


# pgfplots holds every coordinate of every figure in TeX's main memory, which
# pdflatex fixes at five million words, and the thesis has to fit all of these
# figures plus its prose and its hand-drawn TikZ inside that. Line plots are
# therefore thinned before they are written. This costs nothing that print
# could show: the widest of these axes is about 90 mm, so 160 points is already
# finer than the width of the line drawn through them.
#
# Thinning happens on the way out, so the summary statistics quoted in captions
# are computed from the full series and stay exact.
MAX_POINTS = 160


def thin(rows: list[list], limit: int | None = MAX_POINTS) -> list[list]:
    """Reduces a series to at most `limit` evenly spaced points, endpoints kept."""
    if limit is None or len(rows) <= limit:
        return rows
    stride = len(rows) / limit
    kept = {int(i * stride) for i in range(limit)}
    kept |= {0, len(rows) - 1}
    return [row for index, row in enumerate(rows) if index in kept]


def write_data(
    root: Path, name: str, header: list[str], rows: list[list], max_points: int | None = MAX_POINTS
) -> str:
    """Writes one figure's numbers. Pass `max_points=None` to disable thinning."""
    path = root / DATA_DIR / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(thin(rows, max_points))
    return f"{DATA_DIR}/{name}.csv"


def write_tex(root: Path, name: str, body: str) -> Path:
    path = root / TEX_DIR / f"{name}.tex"
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "%!TEX root = ../../thesis.tex\n"
        "% Generated by scripts/evaluate.py -- do not edit; edit the emitter instead.\n"
    )
    path.write_text(header + body)
    return path


def band(
    source: str, x: str, low: str, mid: str, high: str, style: str, fill: str,
    legend: str | None, key: str,
) -> str:
    """A median line inside a quantile band, as four coordinated plots.

    `fill between` needs the two edges of the band to carry names, and those
    names share one namespace per axis, so `key` must be unique within a
    figure. The band edges and the fill are all `forget plot` so that a single
    legend entry describes the whole thing.
    """
    options = style if legend is not None else f"{style}, forget plot"
    entry = "" if legend is None else f"\n    \\addlegendentry{{{legend}}}"
    return f"""    \\addplot [draw=none, forget plot, name path=lo{key}]
      table [col sep=comma, x={x}, y={low}] {{{source}}};
    \\addplot [draw=none, forget plot, name path=hi{key}]
      table [col sep=comma, x={x}, y={high}] {{{source}}};
    \\addplot [{fill}, forget plot] fill between [of=lo{key} and hi{key}];
    \\addplot [{options}]
      table [col sep=comma, x={x}, y={mid}] {{{source}}};{entry}"""


def figure(label: str, caption: str, short: str, body: str, placement: str = "htb") -> str:
    return f"""\\begin{{figure}}[{placement}]
  \\centering
{body}
  \\caption[{short}]{{{caption}}}
  \\label{{fig:{label}}}
\\end{{figure}}
"""


def axis(
    options: str,
    plots: str,
    width: str = "0.44\\textwidth",
    height: str = "4.4cm",
    style: str = "thesis result plot",
) -> str:
    """One pgfplots axis. `style` is defined in preamble/06-thesis.tex."""
    return f"""  \\begin{{tikzpicture}}
    \\begin{{axis}}[{style}, width={width}, height={height},
{options}]
{plots}
    \\end{{axis}}
  \\end{{tikzpicture}}"""


# Panel layout. The text block is 14.5 cm wide and 20.4 cm tall, and the
# template's margins are not ours to borrow, so width is the scarce dimension
# and height is not. Three panels side by side leave each about 4 cm across,
# which is too small to read a curve in; stacking them one per row spends
# vertical space, of which a float has plenty, and gives every panel the full
# text width instead.
#
# Set PANEL_LAYOUT to "row" for the compact side-by-side form. The heights are
# chosen so three stacked panels, their subcaptions and the main caption still
# fit on one page.
PANEL_LAYOUT = "column"
PANEL_WIDTHS = {"column": "0.99\\linewidth", "row": "0.32\\linewidth"}
PANEL_HEIGHTS = {"column": "4.2cm", "row": "4.0cm"}
HEATMAP_HEIGHTS = {"column": "3.6cm", "row": "3.4cm"}


def panel_height(heatmap: bool = False) -> str:
    """The axis height for one panel under the current layout."""
    return (HEATMAP_HEIGHTS if heatmap else PANEL_HEIGHTS)[PANEL_LAYOUT]


def panel(body: str, caption: str, width: str | None = None) -> str:
    """Wraps one axis as a subfigure.

    Per-target panels are labelled with a subcaption rather than a pgfplots
    `title`, because a title occupies the space above the axis that the
    heatmaps need for their colour bar, and because a subcaption is
    referenceable and lands in the list of figures.
    """
    indented = "\n".join("  " + line for line in body.splitlines())
    return f"""  \\begin{{subfigure}}[b]{{{width or PANEL_WIDTHS[PANEL_LAYOUT]}}}
    \\centering
{indented}
    \\caption{{{caption}}}
  \\end{{subfigure}}"""


def panels_row(items: list[str], layout: str | None = None) -> str:
    """Lays panels out under the current layout, or a forced one.

    Side by side they are separated by rubber space; stacked they need an
    explicit line break, since subfigures are boxes in a paragraph and would
    otherwise flow onto the same line. `layout` overrides the default for
    figures whose panels are a grid rather than one panel per target.
    """
    if (layout or PANEL_LAYOUT) == "column":
        return "\n  \\\\[1.4ex]\n".join(items)
    return "\n  \\hfill\n".join(items)


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------


def fig_coverage(root: Path, cache: Path, arms: dict, x_key: str, name: str, x_label: str,
                 scale: float = 1.0, caption_axis: str | None = None):
    """Union coverage against a chosen currency, one panel per target.

    Coverage is per environment: each of the 128 parallel environments keeps
    its own union, and the band spans the 25th to 75th percentile over
    environments and seeds pooled.  The cjson panel carries the random control;
    the other two have none, which the caption states rather than implies.
    """
    panels = []
    described: list[str] = []
    for target, display in TARGETS.items():
        labels = CJSON_HEADLINE if target == "cjson" else [None]
        plots = []
        for i, label in enumerate(labels):
            selected = [
                runs for (t, l), runs in arms.items() if t == target and (label is None or l == label)
            ]
            if not selected:
                continue
            runs = [run for group in selected for run in group]
            series = [load(cache, run, "coverage") for run in runs]
            series = [rows for rows in series if rows]
            if not series:
                continue
            x_pooled = pool_by_index(series, x_key)
            pooled = {
                key: pool_by_index(series, f"cov_{key}") for key in ("q25", "median", "q75")
            }
            rows = []
            for index in sorted(pooled["median"]):
                lo, mid, hi = (
                    min(pooled["q25"][index]),
                    quantiles(pooled["median"][index])[1],
                    max(pooled["q75"][index]),
                )
                x_value = sum(x_pooled[index]) / len(x_pooled[index]) * scale
                rows.append([round(x_value, 4), round(lo, 2), round(mid, 2), round(hi, 2)])
            source = write_data(
                root, f"{name}-{target}-{(label or 'main').lower()}", ["x", "lo", "mid", "hi"], rows
            )
            # The legend carries the bare arm name; a 4 cm panel has no room for
            # the description, which goes in the caption instead.
            legend = label if target == "cjson" else None
            plots.append(band(source, "x", "lo", "mid", "hi", LINE_STYLES[i], BAND_FILLS[i], legend, chr(65 + i)))
            if label in ARM_CAPTIONS:
                described.append(f"{label} is the {ARM_CAPTIONS[label]}")

        options = (
            f"      xlabel={{{x_label}}}, {shared_ylabel('blocks covered', not panels)},\n"
            "      xmin=0, ymin=0, scaled x ticks=false,\n"
            "      legend pos=south east, legend style={font=\\scriptsize}"
        )
        panels.append(panel(axis(options, "\n".join(plots), width="0.95\\linewidth",
                            height=panel_height()), display))
    body = panels_row(panels)
    arms_described = "; ".join(described)
    return write_tex(
        root,
        name,
        figure(
            name,
            f"Union coverage against {(caption_axis or x_label).lower()}. "
            "Coverage is per environment: each of the 128 parallel environments keeps its "
            "own union. The line is the median and the band the interquartile range over "
            "those environments and the four seeds pooled. "
            f"Of the cJSON arms, {arms_described}. "
            "Only the cJSON campaign has a random control arm; the libxml2 and "
            "picohttpparser panels are read against the structural-rate control of "
            "\\cref{fig:structural-rate} instead.",
            f"Union coverage against {(caption_axis or x_label).lower()}",
            body,
            placement="tbp",
        ),
    )


def fig_structural(root: Path, cache: Path, arms: dict):
    """Structural-byte rate per target, per seed, against the chance level.

    This is the within-run control: the rate at iteration 0 is what an
    untrained policy achieves, and the distance from it is the evidence that
    the agent learned the target's grammar from coverage alone.  Every seed is
    drawn individually because the seed spread is itself a result.
    """
    panels = []
    for target, display in TARGETS.items():
        runs = [
            run
            for (t, label), group in arms.items()
            if t == target and not (t == "cjson" and label != "T25")
            for run in group
        ]
        if not runs:
            continue
        series = {run.seed: load(cache, run, "structural") for run in runs}
        series = {seed: rows for seed, rows in series.items() if rows}
        seeds = sorted(series)
        length = min(len(rows) for rows in series.values())
        rows = [
            [i] + [round(num(series[seed][i], "rate"), 5) for seed in seeds] for i in range(length)
        ]
        source = write_data(
            root, f"structural-rate-{target}", ["iteration", *[f"s{s}" for s in seeds]], rows
        )
        chance = sum(num(series[seed][0], "rate") for seed in seeds) / len(seeds)
        plots = [
            f"    \\addplot [{LINE_STYLES[i % len(LINE_STYLES)]}, forget plot]\n"
            f"      table [col sep=comma, x=iteration, y=s{seed}] {{{source}}};"
            for i, seed in enumerate(seeds)
        ]
        plots.append(
            f"    \\addplot [KITblack50, dashed, forget plot] coordinates "
            f"{{(0,{chance:.4f}) ({length - 1},{chance:.4f})}};"
        )
        options = (
            f"      xlabel={{learner iteration}}, "
            f"{shared_ylabel('structural byte rate', not panels)},\n"
            "      xmin=0, ymin=0, ymax=1"
        )
        panels.append(panel(axis(options, "\n".join(plots), width="0.95\\linewidth",
                            height=panel_height()), display))
    body = panels_row(panels)
    return write_tex(
        root,
        "structural-rate",
        figure(
            "structural-rate",
            "Fraction of self-play actions drawn from the target's grammar-relevant byte "
            "set, one line per seed. The dashed line is the untrained rate measured at "
            "iteration 0, which is the chance level and serves as the within-run control. "
            "All three targets rise far above it, and all three peak early and then decay "
            "(\\cref{fig:structural-decay}).",
            "Structural byte rate against training iteration",
            body,
            placement="tbp",
        ),
    )


def fig_structural_decay(root: Path, cache: Path, arms: dict):
    """The peak-then-decay of the structural rate, overlaid across targets.

    Plotted against a normalised training axis so the three campaigns, which
    ran for 200 and 400 iterations, are comparable; the rate itself is already
    a fraction and needs no rescaling.  This is the strongest cross-target
    observation in the campaign: the same shape in three different grammars.
    """
    plots = []
    peaks = []
    for i, (target, display) in enumerate(TARGETS.items()):
        runs = [
            run
            for (t, label), group in arms.items()
            if t == target and not (t == "cjson" and label != "T25")
            for run in group
        ]
        series = [load(cache, run, "structural") for run in runs]
        series = [rows for rows in series if rows]
        if not series:
            continue
        length = min(len(rows) for rows in series)
        rows = []
        for index in range(length):
            values = [num(rows_[index], "rate") for rows_ in series]
            lo, mid, hi = quantiles(values)
            rows.append([round(index / (length - 1), 5), round(lo, 5), round(mid, 5), round(hi, 5)])
        source = write_data(root, f"structural-decay-{target}", ["x", "lo", "mid", "hi"], rows)
        plots.append(band(source, "x", "lo", "mid", "hi", LINE_STYLES[i], BAND_FILLS[i], display, chr(65 + i)))
        peak = max(rows, key=lambda row: row[2])
        peaks.append((display, peak[0], peak[2], rows[-1][2]))

    marks = "\n".join(
        f"    \\addplot [only marks, mark=*, mark size=1.6pt, KITblack, forget plot] "
        f"coordinates {{({x:.4f},{y:.4f})}};"
        for _, x, y, _ in peaks
    )
    options = (
        "      xlabel={training progress (fraction of iterations)},\n"
        "      ylabel={structural byte rate},\n"
        "      xmin=0, xmax=1, ymin=0, ymax=1,\n"
        "      legend pos=south east, legend style={font=\\scriptsize}"
    )
    body = axis(options, "\n".join(plots) + "\n" + marks, width="0.86\\textwidth", height="6.2cm")
    described = "; ".join(
        f"{display} peaks at {peak:.2f} after {100 * x:.0f}\\,\\% of training and ends at {final:.2f}"
        for display, x, peak, final in peaks
    )
    return write_tex(
        root,
        "structural-decay",
        figure(
            "structural-decay",
            "The structural byte rate against normalised training progress, median and "
            "interquartile range over seeds. The abscissa is normalised because the "
            "campaigns ran for different numbers of iterations. Markers denote the peak: "
            f"{described}. Each of the {_count_word(len(peaks))} targets peaks before the "
            "end of training and finishes below its peak, though by different margins and "
            "at very different points in training.",
            "Decay of the structural byte rate after its peak",
            body,
        ),
    )


def fig_return(root: Path, cache: Path, arms: dict):
    """Per-trajectory return, the RL-side learning curve."""
    panels = []
    for target, display in TARGETS.items():
        runs = [
            run
            for (t, label), group in arms.items()
            if t == target and not (t == "cjson" and label not in ("T25", "CTRL-RAND"))
            for run in group
        ]
        by_label: dict[str, list[Run]] = defaultdict(list)
        for run in runs:
            by_label[run.label].append(run)
        plots = []
        for i, (label, group) in enumerate(sorted(by_label.items())):
            series = [rows for rows in (load(cache, run, "return") for run in group) if rows]
            if not series:
                continue
            pooled = {
                key: pool_by_index(series, f"return_{key}", index="iteration")
                for key in ("q25", "median", "q75")
            }
            rows = [
                [
                    index,
                    round(min(pooled["q25"][index]), 4),
                    round(quantiles(pooled["median"][index])[1], 4),
                    round(max(pooled["q75"][index]), 4),
                ]
                for index in sorted(pooled["median"])
            ]
            source = write_data(root, f"return-{target}-{label.lower()}", ["x", "lo", "mid", "hi"], rows)
            legend = label if len(by_label) > 1 else None
            plots.append(band(source, "x", "lo", "mid", "hi", LINE_STYLES[i], BAND_FILLS[i], legend, chr(65 + i)))
        options = (
            f"      xlabel={{learner iteration}}, "
            f"{shared_ylabel('episode return', not panels)},\n"
            "      xmin=0, ymin=0, legend pos=south east, legend style={font=\\scriptsize}"
        )
        panels.append(panel(axis(options, "\n".join(plots), width="0.95\\linewidth",
                            height=panel_height()), display))
    body = panels_row(panels)
    return write_tex(
        root,
        "return",
        figure(
            "return",
            "Per-trajectory return, median and interquartile range over the 128 environments "
            "and four seeds. Return is the reward the agent optimises and rises monotonically "
            "on all three targets, which is what distinguishes it from the coverage curves: "
            "the agent keeps improving on its own objective after coverage has saturated.",
            "Episode return against training iteration",
            body,
            placement="tbp",
        ),
    )


LOSS_SERIES = ["total", "value", "policy", "value_prefix", "simsiam"]


def _loss_data(root: Path, cache: Path, chosen: dict, prefix: str) -> tuple[dict, dict]:
    """Writes one loss table per target and pools the plotted values per series.

    The pooled values are what decides each panel's ordinate scale, which
    cannot be decided from the name of the loss; see `_loss_panels`.
    """
    sources: dict[str, str] = {}
    pooled: dict[str, list[float]] = defaultdict(list)
    for target, run in chosen.items():
        if run is None:
            continue
        rows_in = load(cache, run, "loss")
        if not rows_in:
            continue
        rows = []
        for row in rows_in:
            cells = [round(num(row, f"{s}_mean"), 5) for s in LOSS_SERIES]
            rows.append([int(float(row["train_batches"]))] + cells)
            for series, value in zip(LOSS_SERIES, cells):
                if value == value:  # not NaN
                    pooled[series].append(value)
        sources[target] = write_data(root, f"{prefix}-{target}", ["batches", *LOSS_SERIES], rows)
    return sources, pooled


def _loss_panels(sources: dict, pooled: dict, display_of: dict) -> str:
    """One small panel per loss, three to a row."""
    panels = []
    for name in LOSS_SERIES:
        plots = [
            f"    \\addplot [{LINE_STYLES[i]}, {'forget plot' if name != 'total' else ''}]\n"
            f"      table [col sep=comma, x=batches, y={name}] {{{source}}};"
            + (f"\n    \\addlegendentry{{{display_of[target]}}}" if name == "total" else "")
            for i, (target, source) in enumerate(sources.items())
        ]
        # pgfplots drops every non-positive coordinate of a logarithmic axis
        # without saying so, which would quietly delete most of a curve rather
        # than fail. The scale is therefore taken from the data and not from
        # the name of the loss. Two of the five can go non-positive: the
        # consistency loss is a negative cosine similarity throughout, and the
        # total carries it with a coefficient of two, so the total turns
        # negative on any target whose supervised terms fall below it.
        values = pooled.get(name) or []
        mode = "      ymode=log,\n" if values and min(values) > 0 else ""
        options = (
            "      xlabel={training batches}, ylabel={" + name.replace("_", r"\_") + "},\n"
            + mode
            + "      title style={font=\\small}, scaled x ticks=base 10:-3,\n"
            "      legend pos=north east, legend style={font=\\scriptsize}"
        )
        panels.append(panel(axis(options, "\n".join(plots), width="0.88\\linewidth", height="3.6cm"),
                            name.replace("_", " "), width="0.32\\linewidth"))
    # The five losses are a grid of small panels, not one panel per
    # target, so they stay three to a row whatever the default layout is.
    return (panels_row(panels[:3], layout="row") + "\n\n  \\vspace{1.4em}\n\n"
            + panels_row(panels[3:], layout="row"))


def fig_losses(root: Path, cache: Path, arms: dict):
    """The five EfficientZero training losses, one panel per loss.

    A training-health diagnostic rather than a result, which is why it belongs
    in the appendix: it says the optimiser behaved, not that the agent fuzzed.
    """
    chosen = {
        target: next(
            (group[0] for (t, label), group in sorted(arms.items()) if t == target and label in ("T25", "LIBXML2-400", "PICOHTTPPARSER-400")),
            None,
        )
        for target in TARGETS
    }
    sources, pooled = _loss_data(root, cache, chosen, "loss")
    if not sources:
        return None
    return write_tex(
        root,
        "losses",
        figure(
            "losses",
            "The five EfficientZero training losses against training batches, for one "
            "representative run per target. Logarithmic ordinate except for the "
            "self-supervised consistency loss, which is a negative cosine similarity and "
            "crosses zero.",
            "EfficientZero training losses",
            _loss_panels(sources, pooled, TARGETS),
            placement="tbp",
        ),
    )


def fig_improvement(root: Path, cache: Path, arms: dict):
    """Whether search improves on the prior or merely echoes it.

    Two quantities per target: the KL divergence between the MCTS visit
    distribution at the root and the network's policy prior, and the entropies
    of both.  A run whose search contributes nothing has a KL that decays to
    zero and a posterior entropy that tracks the prior.
    """
    panels = []
    for target, display in TARGETS.items():
        runs = [
            run
            for (t, label), group in arms.items()
            if t == target and not (t == "cjson" and label != "T25")
            for run in group
        ]
        series = [rows for rows in (load(cache, run, "improvement") for run in runs) if rows]
        if not series:
            continue
        keys = ["selfplay_kl_mean", "selfplay_prior_entropy", "selfplay_posterior_entropy"]
        pooled = {key: pool_by_index(series, key, index="iteration") for key in keys}
        rows = [
            [index] + [round(quantiles(pooled[key][index])[1], 5) for key in keys]
            for index in sorted(pooled[keys[0]])
        ]
        source = write_data(root, f"improvement-{target}", ["iteration", *keys], rows)
        plots = [
            f"    \\addplot [{LINE_STYLES[i]}] table [col sep=comma, x=iteration, y={key}] {{{source}}};"
            f"\n    \\addlegendentry{{{name}}}"
            for i, (key, name) in enumerate(
                zip(keys, ["search vs.\\ prior (KL)", "prior entropy", "posterior entropy"])
            )
        ]
        options = (
            f"      xlabel={{learner iteration}}, {shared_ylabel('nats', not panels)},\n"
            "      xmin=0, ymin=0, legend pos=north east, legend style={font=\\scriptsize}"
        )
        panels.append(panel(axis(options, "\n".join(plots), width="0.95\\linewidth",
                            height=panel_height()), display))
    body = panels_row(panels)
    return write_tex(
        root,
        "policy-improvement",
        figure(
            "policy-improvement",
            "What search contributes at the root during self-play: the KL divergence between "
            "the MCTS visit distribution and the policy prior, against the entropies of "
            "both, as medians over seeds. A KL that stays clear of zero is the evidence "
            "that planning moves the policy rather than reproducing it.",
            "Policy improvement of search over the prior",
            body,
            placement="tbp",
        ),
    )


# A `matrix plot` becomes one enormous TeX path, and pdflatex runs out of main
# memory somewhere above ten thousand cells -- the full 400 x 128 matrix is
# 51 200. These caps keep a three-panel figure well inside that budget, and no
# resolution is lost that the printed figure could have shown anyway: at
# 0.26\textwidth a panel is about 45 mm wide, so 80 columns is already finer
# than half a millimetre per cell.
HEATMAP_COLUMNS = 64
HEATMAP_ROWS = 24


def _heatmap(root: Path, cache: Path, arms: dict, source_name: str, value_key: str,
             name: str, label_text: str, caption: str, short: str, colormap: str):
    """A position x iteration matrix per target, drawn as a matrix plot.

    Both axes are binned by averaging rather than subsampled. Subsampling a
    collapse diagnostic is the one thing that could turn a noisy signal into a
    clean-looking one by luck of which iterations were kept; averaging cannot.
    """
    panels = []
    for target, display in TARGETS.items():
        run = next(
            (
                group[0]
                for (t, label), group in sorted(arms.items())
                if t == target and not (t == "cjson" and label != "T25")
            ),
            None,
        )
        if run is None:
            continue
        rows_in = load(cache, run, source_name)
        if not rows_in:
            continue
        iterations = sorted({int(float(row["iteration"])) for row in rows_in})
        positions_in = sorted({int(float(row["position"])) for row in rows_in})
        col_width = max(1, -(-len(iterations) // HEATMAP_COLUMNS))
        row_height = max(1, -(-len(positions_in) // HEATMAP_ROWS))
        col_of = {value: index // col_width for index, value in enumerate(iterations)}
        row_of = {value: index // row_height for index, value in enumerate(positions_in)}

        cells: dict[tuple[int, int], list[float]] = defaultdict(list)
        for row in rows_in:
            value = num(row, value_key)
            if value == value:  # not NaN
                key = (col_of[int(float(row["iteration"]))], row_of[int(float(row["position"]))])
                cells[key].append(value)
        # Label each bin with the iteration and position at its centre, so the
        # axes still read in the units of the underlying measurement.
        rows = sorted(
            [
                iterations[min(len(iterations) - 1, col * col_width + col_width // 2)],
                positions_in[min(len(positions_in) - 1, position * row_height + row_height // 2)],
                round(sum(values) / len(values), 5),
            ]
            for (col, position), values in cells.items()
        )
        positions = len({row[1] for row in rows})
        source = write_data(root, f"{name}-{target}", ["iteration", "position", "value"], rows, max_points=None)
        plots = (
            f"    \\addplot [matrix plot*, point meta=explicit, mesh/cols={positions}]\n"
            f"      table [col sep=comma, x=iteration, y=position, meta=value] {{{source}}};"
        )
        # The colour bar goes underneath, lying down. Standing upright beside
        # the axis its tick labels cost some 45 pt of width per panel, which
        # three panels cannot afford, and that cost is fixed -- narrowing the
        # plot to make room makes the overflow worse, not better. Below the
        # abscissa label it costs height instead, of which there is plenty.
        # `axis lines=left` has to be undone for the bar itself, or the parent
        # style draws a heavy rule along one side of it.
        options = (
            f"      xlabel={{learner iteration}}, "
            f"{shared_ylabel('episode step', not panels)},\n"
            f"      colormap/{colormap}, colorbar horizontal,\n"
            "      colorbar style={font=\\scriptsize, height=0.14cm, axis lines=box,\n"
            "        axis line style={KITblack50, thin}, tick align=outside,\n"
            "        at={(0.5,-0.72)}, anchor=north, xtick align=outside,\n"
            "        width=0.9*\\pgfkeysvalueof{/pgfplots/parent axis width}}"
        )
        panels.append(
            panel(
                axis(options, plots, width="0.95\\linewidth", height=panel_height(heatmap=True),
                     style="thesis matrix plot"),
                display,
            )
        )
    body = panels_row(panels)
    colour = f" Colour encodes {label_text}."
    return write_tex(root, name, figure(name, caption + colour, short, body, placement="tbp"))


def fig_collapse(root: Path, cache: Path, arms: dict):
    return _heatmap(
        root, cache, arms, "collapse", "entropy", "collapse-entropy",
        "visit entropy (nats)",
        "Shannon entropy of the MCTS root visit counts at each episode-step position, over "
        "training, for one representative run per target. Entropy collapsing towards zero "
        "across all positions is the signature of a policy that has stopped exploring; the "
        "positions collapse in order, earliest first.",
        "MCTS visit entropy per episode-step position",
        "viridis",
    )


def fig_depth_actions(root: Path, cache: Path, arms: dict):
    return _heatmap(
        root, cache, arms, "depth_actions", "top_share", "depth-actions",
        "share of the most-played action",
        "The share of self-play plays taken by the single most-played action at each "
        "episode-step position, over training. This is the policy-collapse matrix: a share "
        "approaching one means the agent plays one fixed byte at that position regardless "
        "of state. Read together with \\cref{fig:structural-rate}, it distinguishes a run "
        "that learned the grammar from one that found a single high-reward token.",
        "Policy-collapse matrix",
        "hot",
    )


def fig_ablation_strip(root: Path, cache: Path, arms: dict):
    """Every cjson run's final coverage, one mark per seed.

    A strip plot rather than bars with error whiskers: with four seeds the
    honest presentation is every run, and the spread within an arm is the
    quantity the ablation has to beat to mean anything.
    """
    entries = []
    for (target, label), runs in sorted(arms.items()):
        if target != "cjson":
            continue
        finals = [
            load_summary(cache, run).get("coverage_final_median") for run in runs
        ]
        finals = [value for value in finals if value]
        if finals:
            entries.append((label, sorted(finals)))
    entries.sort(key=lambda item: sum(item[1]) / len(item[1]))

    rows = [
        [index, label, round(value, 2)]
        for index, (label, values) in enumerate(entries)
        for value in values
    ]
    source = write_data(root, "ablation-strip", ["y", "arm", "coverage"], rows, max_points=None)
    medians = [
        [index, round(sorted(values)[len(values) // 2], 2)] for index, (label, values) in enumerate(entries)
    ]
    median_source = write_data(root, "ablation-strip-median", ["y", "coverage"], medians, max_points=None)
    ticks = ",".join(str(i) for i in range(len(entries)))
    tick_labels = ",".join(label for label, _ in entries)
    plots = (
        f"    \\addplot [KIT scatter plot A, mark size=1.6pt, opacity=0.75]\n"
        f"      table [col sep=comma, x=coverage, y=y] {{{source}}};\n"
        f"    \\addplot [only marks, mark=|, mark size=4pt, KITred, very thick]\n"
        f"      table [col sep=comma, x=coverage, y=y] {{{median_source}}};"
    )
    options = (
        "      xlabel={blocks covered at the end of training}, ylabel={},\n"
        "      axis y line=left, axis x line=bottom,\n"
        f"      ytick={{{ticks}}}, yticklabels={{{tick_labels}}},\n"
        "      yticklabel style={font=\\scriptsize}, ymin=-0.7, "
        f"ymax={len(entries) - 0.3}, xmin=0"
    )
    body = axis(options, plots, width="0.80\\textwidth", height=f"{0.62 * len(entries):.1f}cm")
    return write_tex(
        root,
        "ablation-strip",
        figure(
            "ablation-strip",
            "Final union coverage of every cJSON run, one mark per seed and a red rule at "
            "the arm median, arms ordered by mean. Plotted per run rather than as a mean "
            "with a standard deviation because the within-arm spread is comparable to the "
            "between-arm differences for most of the campaign --- the two temperature arms "
            "are the clear exception.",
            "Final coverage of every cJSON ablation run",
            body,
            placement="tbp",
        ),
    )


def fig_saturation(root: Path, cache: Path, arms: dict):
    """Coverage normalised to each run's own final level, across targets.

    The one legitimate cross-target overlay: normalising removes the two orders
    of magnitude separating picohttpparser from libxml2 and leaves the question
    the comparison is actually about, which is how quickly each target is
    exhausted.
    """
    plots = []
    described = []
    for i, (target, display) in enumerate(TARGETS.items()):
        runs = [
            run
            for (t, label), group in arms.items()
            if t == target and not (t == "cjson" and label != "T25")
            for run in group
        ]
        series = [rows for rows in (load(cache, run, "coverage") for run in runs) if rows]
        if not series:
            continue
        normalised = []
        for rows in series:
            start, final = num(rows[0], "cov_median"), num(rows[-1], "cov_median")
            span = final - start
            normalised.append(
                [(num(row, "executions_per_env"), (num(row, "cov_median") - start) / span if span else 0.0)
                 for row in rows]
            )
        length = min(len(rows) for rows in normalised)
        rows = []
        for index in range(length):
            values = [run[index][1] for run in normalised]
            x_value = sum(run[index][0] for run in normalised) / len(normalised)
            lo, mid, hi = quantiles(values)
            rows.append([round(x_value), round(lo, 5), round(mid, 5), round(hi, 5)])
        source = write_data(root, f"saturation-{target}", ["x", "lo", "mid", "hi"], rows)
        plots.append(band(source, "x", "lo", "mid", "hi", LINE_STYLES[i], BAND_FILLS[i], display, chr(65 + i)))

        # Every curve ends at one by construction, so the figure cannot show
        # whether a target had stopped gaining coverage -- only when it reached
        # its own ceiling. The share of the total gain that falls in the last
        # quarter of the budget is what distinguishes exhausted from truncated,
        # and it is stated rather than left to the eye.
        reach90 = next(
            (row[0] for row in rows if row[2] >= 0.9), rows[-1][0]
        ) / max(rows[-1][0], 1)
        tail = rows[-1][2] - rows[int(len(rows) * 0.75)][2]
        described.append(
            f"{display} reaches 90\\,\\% of its final coverage after {100 * reach90:.0f}\\,\\% "
            f"of the budget and gains a further {100 * tail:.0f}\\,\\% of its total in the "
            "last quarter"
        )
    options = (
        "      xlabel={executions per environment}, ylabel={fraction of final coverage},\n"
        "      xmin=0, ymin=0, ymax=1.02, scaled x ticks=base 10:-3,\n"
        "      legend pos=south east, legend style={font=\\scriptsize}"
    )
    body = axis(options, "\n".join(plots), width="0.86\\textwidth", height="6.2cm")
    return write_tex(
        root,
        "saturation",
        figure(
            "saturation",
            "Coverage normalised to each run's own final level, against executions per "
            "environment, as medians over seeds. Normalising is what makes the three "
            "targets comparable at all, since they instrument different numbers of basic "
            "blocks. Note that every curve ends at one by construction, so the figure shows "
            "when each target reached its own ceiling and not whether that ceiling is a "
            f"true plateau. {'; '.join(described)}.",
            "Coverage saturation across the three targets",
            body,
        ),
    )


def fig_tree(root: Path, cache: Path, arms: dict):
    """Distinct action prefixes discovered, by trie depth."""
    plots = []
    for i, (target, display) in enumerate(TARGETS.items()):
        run = next(
            (
                group[0]
                for (t, label), group in sorted(arms.items())
                if t == target and not (t == "cjson" and label != "T25")
            ),
            None,
        )
        if run is None:
            continue
        rows_in = load(cache, run, "tree")
        if not rows_in:
            continue
        by_depth: dict[int, int] = defaultdict(int)
        for row in rows_in:
            by_depth[int(float(row["depth"]))] += int(float(row["new_nodes"]))
        rows = [[depth, by_depth[depth]] for depth in sorted(by_depth)]
        source = write_data(root, f"tree-{target}", ["depth", "nodes"], rows, max_points=None)
        plots.append(
            f"    \\addplot [{LINE_STYLES[i]}] table [col sep=comma, x=depth, y=nodes] {{{source}}};"
            f"\n    \\addlegendentry{{{display}}}"
        )
    options = (
        "      xlabel={trie depth (episode step)}, ylabel={distinct prefixes reached},\n"
        "      ymode=log, xmin=0, legend pos=south east, legend style={font=\\scriptsize}"
    )
    body = axis(options, "\n".join(plots), width="0.86\\textwidth", height="6.2cm")
    return write_tex(
        root,
        "tree-depth",
        figure(
            "tree-depth",
            "Distinct action prefixes the run ever executed, by depth in the action-execution "
            "trie, for one representative run per target. The shape separates search that "
            "goes deep and narrow from search that goes broad and shallow; a trie that "
            "widens without deepening is the signature of the corpus formulation spending "
            "its budget on variations of the same prefix.",
            "Action-trie breadth by depth",
            body,
        ),
    )


def fig_buffer(root: Path, cache: Path, arms: dict):
    """Reward density in the replay buffer.

    Read this against the reward's actual scope, not the run's. `Marginal`
    scores novelty against the corpus union of the *current episode*, and
    `reset` re-bootstraps that corpus (`mugiwara/examples/cjson.rs`), so a block
    found in one episode pays again in the next and the signal cannot thin out
    as run-level coverage saturates. The share rises with competence instead.
    """
    plots = []
    for i, (target, display) in enumerate(TARGETS.items()):
        runs = [
            run
            for (t, label), group in arms.items()
            if t == target and not (t == "cjson" and label != "T25")
            for run in group
        ]
        series = [rows for rows in (load(cache, run, "buffer") for run in runs) if rows]
        if not series:
            continue
        pooled = pool_by_index(series, "rewarded_step_share", index="iteration")
        rows = [[index, round(quantiles(pooled[index])[1], 6)] for index in sorted(pooled)]
        source = write_data(root, f"buffer-{target}", ["iteration", "rewarded_step_share"], rows)
        plots.append(
            f"    \\addplot [{LINE_STYLES[i]}] table [col sep=comma, x=iteration, "
            f"y=rewarded_step_share] {{{source}}};\n    \\addlegendentry{{{display}}}"
        )
    options = (
        "      xlabel={learner iteration}, ylabel={share of buffer steps carrying reward},\n"
        "      xmin=0, ymin=0, legend pos=north west, legend style={font=\\scriptsize}"
    )
    body = axis(options, "\n".join(plots), width="0.86\\textwidth", height="5.8cm")
    return write_tex(
        root,
        "buffer-reward-density",
        figure(
            "buffer-reward-density",
            "The fraction of replay-buffer transitions that carry a non-zero reward. Coverage "
            "rewards are sparse --- a step pays only when it reaches a block the episode had "
            "not reached before --- but they are scored against the corpus union of the "
            "current episode, which is re-bootstrapped at every reset, so a block found once "
            "pays again in the next episode and the signal does not thin out as run-level "
            "coverage saturates. The share rises with competence instead, as the agent finds "
            "more new blocks per episode. libxml2 is the one target that turns over, peaking "
            "at \\num{0.201} and ending at \\num{0.188}.",
            "Reward density in the replay buffer",
            body,
        ),
    )


# --------------------------------------------------------------------------
# Input-level action spaces
#
# One run per target and one seed per run, so these figures draw a line rather
# than a band across seeds. Where a band appears it is the spread across the
# 128 environments within one learner iteration, which is a different quantity
# from the seed spread of the corpus figures and is named as such in every
# caption. Two panels per figure rather than three, side by side.
# --------------------------------------------------------------------------


INPUT_PANEL_WIDTH = "0.48\\linewidth"
INPUT_AXIS_WIDTH = "0.95\\linewidth"
INPUT_AXIS_HEIGHT = "4.0cm"


def input_run(arms: dict, target: str) -> Run | None:
    """The single run of an input-level campaign."""
    return next(
        (group[0] for (t, _), group in sorted(arms.items()) if t == target and group),
        None,
    )


def input_panel(options: str, plots: list[str], caption: str) -> str:
    return panel(
        axis(options, "\n".join(plots), width=INPUT_AXIS_WIDTH, height=INPUT_AXIS_HEIGHT),
        caption,
        width=INPUT_PANEL_WIDTH,
    )


def input_grid(panels: list[str]) -> str:
    """Lays panels out two to a row."""
    rows = [panels[i : i + 2] for i in range(0, len(panels), 2)]
    return "\n\n  \\vspace{1.4em}\n\n".join(panels_row(row, layout="row") for row in rows)


def fig_input_learning(root: Path, cache: Path, arms: dict):
    """That each input-level target was solved, in the terms of that target.

    Return is the quantity the agent optimises and is comparable to nothing
    outside its own target, so each target gets a second panel in a unit that
    can be read directly: for high-and-low the fraction of self-play bytes that
    take the high-coverage branch, against the measured chance rate; for
    sequence the trajectory length, which because the program exits on the
    first wrong byte is exactly the number of passcode bytes the agent has
    right. Both make "solved" a value on the ordinate rather than an assertion.
    """
    panels = []
    for target, display in INPUT_TARGETS.items():
        run = input_run(arms, target)
        if run is None:
            continue

        returns = load(cache, run, "return")
        if returns:
            rows = [
                [
                    int(float(row["iteration"])),
                    round(num(row, "return_q25"), 4),
                    round(num(row, "return_median"), 4),
                    round(num(row, "return_q75"), 4),
                ]
                for row in returns
            ]
            source = write_data(root, f"input-return-{target}", ["x", "lo", "mid", "hi"], rows)
            options = (
                "      xlabel={learner iteration}, ylabel={episode return},\n"
                "      xmin=0, ymin=0"
            )
            panels.append(
                input_panel(
                    options,
                    [band(source, "x", "lo", "mid", "hi", LINE_STYLES[0], BAND_FILLS[0], None, "R")],
                    f"{display}: return",
                )
            )

        # The second panel is the target's own evidence, and there is one per
        # target because the two targets record different probes.
        rates = load(cache, run, "structural")
        lengths = load(cache, run, "length")
        if rates:
            rows = [
                [int(float(row["iteration"])), round(num(row, "rate"), 5)] for row in rates
            ]
            source = write_data(root, f"input-rate-{target}", ["iteration", "rate"], rows)
            chance = num(rates[0], "rate")
            plots = [
                f"    \\addplot [{LINE_STYLES[0]}, forget plot]\n"
                f"      table [col sep=comma, x=iteration, y=rate] {{{source}}};",
                f"    \\addplot [KITblack50, dashed, forget plot] coordinates "
                f"{{(0,{chance:.5f}) ({rows[-1][0]},{chance:.5f})}};",
            ]
            options = (
                "      xlabel={learner iteration}, ylabel={high-coverage byte rate},\n"
                "      xmin=0, ymin=0, ymax=1"
            )
            panels.append(input_panel(options, plots, f"{display}: action rate"))
        elif lengths:
            rows = [
                [
                    int(float(row["iteration"])),
                    round(num(row, "length_q25"), 4),
                    round(num(row, "length_median"), 4),
                    round(num(row, "length_q75"), 4),
                ]
                for row in lengths
            ]
            source = write_data(root, f"input-length-{target}", ["x", "lo", "mid", "hi"], rows)
            plots = [band(source, "x", "lo", "mid", "hi", LINE_STYLES[1], BAND_FILLS[1], None, "L")]
            ceiling = INPUT_EPISODE_CEILING.get(target)
            if ceiling:
                plots.append(
                    f"    \\addplot [KITblack50, dashed, forget plot] coordinates "
                    f"{{(0,{ceiling:g}) ({rows[-1][0]},{ceiling:g})}};"
                )
            options = (
                "      xlabel={learner iteration}, ylabel={episode length},\n"
                "      xmin=0, ymin=0"
            )
            panels.append(input_panel(options, plots, f"{display}: episode length"))

    if not panels:
        return None
    return write_tex(
        root,
        "input-learning",
        figure(
            "input-learning",
            "Learning on the two input-level targets. The left column is the episode return, "
            "the quantity the agent optimises, as the median over the 128 environments of one "
            "learner iteration inside their interquartile range; each target ran once, so the "
            "band is the spread across environments and not across seeds. The right column "
            "restates the same run in the target's own units. For high-and-low the dashed "
            "line is the rate at which an untrained policy hits the high-coverage branch, "
            "measured at iteration 0; for sequence the dashed line is the full 16-byte "
            "passcode, and since the program exits on the first wrong byte the episode length "
            "is the length of the correct prefix.",
            "Learning on the input-level targets",
            input_grid(panels),
            placement="tbp",
        ),
    )


def fig_input_losses(root: Path, cache: Path, arms: dict):
    """The five EfficientZero training losses on the input-level targets.

    The same training-health diagnostic as \\cref{fig:losses} carries for the
    corpus targets: it says the optimiser behaved, not that the agent fuzzed.
    It matters more here than there, because these two targets exist to test
    the learner rather than the fuzzer.
    """
    chosen = {target: input_run(arms, target) for target in INPUT_TARGETS}
    sources, pooled = _loss_data(root, cache, chosen, "loss")
    if not sources:
        return None
    return write_tex(
        root,
        "input-losses",
        figure(
            "input-losses",
            "The five EfficientZero training losses on the two input-level targets, against "
            "training batches. Logarithmic ordinate on the three supervised losses, which "
            "stay positive; linear on the consistency loss, which is a negative cosine "
            "similarity, and on the total, which carries the consistency loss with a "
            "coefficient of two and therefore turns negative once the supervised terms fall "
            "below it. The two targets ran for different numbers of iterations, so their "
            "curves end at different batch counts.",
            "Training losses on the input-level targets",
            _loss_panels(sources, pooled, INPUT_TARGETS),
            placement="tbp",
        ),
    )


def fig_input_entropy(root: Path, cache: Path, arms: dict):
    """Entropy of the played action distribution, against the uniform policy.

    This quantity is pooled over episode positions, which is why the two
    targets look so different and why the sequence curve must not be read as a
    failure to converge.  high-and-low wants the same byte at every position,
    so the pooled entropy is the per-state entropy and collapses with it.
    sequence wants a different byte at each of its sixteen positions, so a
    policy that is deterministic everywhere still pools to about ln 16, and
    that is where the curve settles.  Per-state determinism on sequence is
    visible in the visit counts, not here.
    """
    panels = []
    for target, display in INPUT_TARGETS.items():
        run = input_run(arms, target)
        rows_in = load(cache, run, "sampled") if run else []
        rows_in = [row for row in rows_in if num(row, "action_entropy") == num(row, "action_entropy")]
        if not rows_in:
            continue
        rows = [
            [int(float(row["iteration"])), round(num(row, "action_entropy"), 5)]
            for row in rows_in
        ]
        source = write_data(root, f"input-entropy-{target}", ["iteration", "entropy"], rows)
        uniform = math.log(INPUT_ACTION_SPACE[target])
        plots = [
            f"    \\addplot [{LINE_STYLES[0]}, forget plot]\n"
            f"      table [col sep=comma, x=iteration, y=entropy] {{{source}}};",
            f"    \\addplot [KITblack50, dashed, forget plot] coordinates "
            f"{{(0,{uniform:.4f}) ({rows[-1][0]},{uniform:.4f})}};",
        ]
        options = (
            "      xlabel={learner iteration}, ylabel={action entropy (nats)},\n"
            f"      xmin=0, ymin=0, ymax={uniform * 1.12:.3f}"
        )
        panels.append(input_panel(options, plots, display))
    if not panels:
        return None
    return write_tex(
        root,
        "input-entropy",
        figure(
            "input-entropy",
            "Shannon entropy of the actions in the batches trained on, for the two "
            "input-level targets. The dashed line is the entropy of the uniform policy over "
            "the target's action space, $\\ln 256 \\approx 5.55$ for high-and-low and "
            "$\\ln 26 \\approx 3.26$ for sequence, which is where an untrained agent starts. "
            "The quantity is pooled over episode positions, which is what makes the two "
            "curves differ in kind. high-and-low rewards the same byte at every position, so "
            "the pooled entropy is the per-state entropy and collapses with it. sequence "
            "rewards a different byte at each of its sixteen positions, so a policy that is "
            "deterministic at every position still pools to about $\\ln 16 \\approx 2.77$, "
            "which is where the curve settles; that value is evidence of a solved passcode "
            "and not of a policy that failed to converge.",
            "Action entropy on the input-level targets",
            input_grid(panels),
            placement="tbp",
        ),
    )


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def tab_campaign(root: Path, cache: Path, arms: dict):
    """Inventory of every run behind the results chapter.

    Reports iterations and revisions as ranges and sets rather than as the
    first seed's value. Two things would otherwise be hidden that a reader
    checking reproducibility needs: six cJSON runs stopped short of 200
    iterations, and the libxml2 and picohttpparser campaigns each ran two of
    their four seeds on a different binary.
    """
    lines = []
    split_arms = []
    for (target, label), runs in sorted(arms.items()):
        # The input-level runs record no coverage probe, so every column this
        # table is built around would be empty for them.
        if target not in TARGETS:
            continue
        summaries = [load_summary(cache, run) for run in runs]
        summaries = [s for s in summaries if s]
        if not summaries:
            continue
        hours = [s.get("wall_hours", 0.0) for s in summaries]
        finals = sorted(s.get("coverage_final_median", 0.0) for s in summaries)
        lengths = sorted({s.get("iterations", 0) for s in summaries})
        shas = sorted({s.get("git_sha", "")[:7] for s in summaries})
        temperature = summaries[0].get("temperature")
        if len(shas) > 1:
            split_arms.append((TARGETS.get(target, target), shas))
        lines.append(
            " & ".join(
                [
                    TARGETS.get(target, target),
                    label.replace("_", r"\_"),
                    str(len(runs)),
                    str(lengths[-1]) if len(lengths) == 1 else f"{lengths[0]}--{lengths[-1]}",
                    f"{temperature:g}" if temperature else "sched.",
                    f"{summaries[0].get('root_dirichlet_alpha', 0):.4g}",
                    f"{finals[len(finals) // 2]:.0f}",
                    f"{finals[0]:.0f}--{finals[-1]:.0f}",
                    f"{sum(hours) / len(hours):.1f}",
                    # One revision per cell keeps the column narrow; a split arm
                    # is flagged and its second revision named in the caption.
                    r"\texttt{" + shas[0] + "}" + (r"$^{\dagger}$" if len(shas) > 1 else ""),
                ]
            )
            + r" \\"
        )
    caveat = (
        (
            " $^{\\dagger}$Not homogeneous: "
            + "; ".join(
                f"{name} ran its seeds on "
                + " and ".join(r"\texttt{" + sha + "}" for sha in shas)
                for name, shas in sorted(split_arms)
            )
            + ". Those seeds are therefore not repeated samples of one configuration."
        )
        if split_arms
        else ""
    )
    body = f"""\\begin{{table}}[tbp]
  \\centering
  \\caption[Campaign inventory]{{Every corpus-action run behind \\cref{{chap:results}};
    the two input-action targets are single runs and are inventoried in
    \\cref{{sec:results-input-actions}}. Coverage is the
    median over the 128 environments at the end of training; the range spans the seeds.
    Wall-clock is the mean per run. An iteration count given as a range means the arm
    holds runs that stopped short. The three campaigns were built from different
    revisions, which is why the revision is reported per arm.{caveat}}}
  \\label{{tab:campaign-inventory}}
  \\footnotesize
  \\setlength{{\\tabcolsep}}{{4pt}}
  \\begin{{tabular}}{{@{{}}llrrrrrrrl@{{}}}}
    \\toprule
    Target & Arm & $n$ & Iter. & $T$ & $\\xi$ & Cov. & Range & Hours & Revision \\\\
    \\midrule
{chr(10).join('    ' + line for line in lines)}
    \\bottomrule
  \\end{{tabular}}
\\end{{table}}
"""
    return write_tex(root, "tab-campaign-inventory", body)


CONTROL_ARM = "CTRL-RAND"
DEEP_SEED_PERCENTILE = 0.99


def _histogram(rows: list[dict]) -> dict[int, int]:
    return {int(float(r["score"])): int(float(r["episodes"])) for r in rows}


def _rate_above(hist: dict[int, int], threshold: int) -> float:
    total = sum(hist.values())
    return 100.0 * sum(n for s, n in hist.items() if s >= threshold) / total if total else 0.0


def tab_deep_seed(root: Path, cache: Path, arms: dict):
    """The campaign's registered primary metric, recomputed from the databases.

    The fraction of episodes whose best seed clears the 99th percentile of the
    pooled control distribution. The threshold is derived once, from all four
    control runs pooled, and every arm is then scored against that one number
    -- scoring each arm against its own distribution would compare each arm to
    itself.

    Only cjson has a random control, so the metric exists for cjson alone; the
    other two campaigns have no floor to measure against.
    """
    control = [
        _histogram(load(cache, run, "episode_scores"))
        for (target, label), group in arms.items()
        if target == "cjson" and label == CONTROL_ARM
        for run in group
    ]
    control = [h for h in control if h]
    if not control:
        return None

    pooled: dict[int, int] = defaultdict(int)
    for hist in control:
        for score, count in hist.items():
            pooled[score] += count
    total = sum(pooled.values())
    # The percentile of the pooled sample, by the same nearest-rank convention
    # the rest of the pipeline uses for quantiles.
    wanted = int(round(DEEP_SEED_PERCENTILE * (total - 1)))
    seen = 0
    threshold = min(pooled)
    for score in sorted(pooled):
        seen += pooled[score]
        if seen > wanted:
            threshold = score
            break

    lines = []
    for (target, label), group in sorted(arms.items()):
        if target != "cjson":
            continue
        rates = [
            _rate_above(hist, threshold)
            for hist in (_histogram(load(cache, run, "episode_scores")) for run in group)
            if hist
        ]
        if not rates:
            continue
        cells = [f"{r:.2f}" for r in rates] + [""] * (4 - len(rates))
        lines.append(
            f"\\texttt{{{label}}} & " + " & ".join(cells)
            + f" & \\textbf{{{sum(rates) / len(rates):.2f}}} \\\\"
        )

    body = f"""\\begin{{table}}[tbp]
  \\centering
  \\caption[Deep-seed rate on cJSON]{{The campaign's registered primary metric on cJSON:
    the percentage of episodes whose best seed reaches the 99th percentile of the pooled
    \\texttt{{{CONTROL_ARM}}} distribution. That percentile is computed once over all
    \\num{{{total}}} control episodes, giving a threshold of \\num{{{threshold}}} covered blocks,
    and every arm is scored against it. The control sits at its own definition; every trained arm
    clears it by roughly two orders of magnitude, and no trained arm is separated from
    another. Only cJSON has a random control, so the metric exists for cJSON alone.}}
  \\label{{tab:deep-seed}}
  \\footnotesize
  \\begin{{tabular}}{{@{{}}lrrrrr@{{}}}}
    \\toprule
    Arm & s00 & s01 & s02 & s03 & Mean \\\\
    \\midrule
{chr(10).join('    ' + line for line in lines)}
    \\bottomrule
  \\end{{tabular}}
\\end{{table}}
"""
    return write_tex(root, "tab-deep-seed", body)


# Seeds are 16 bytes on cJSON and 32 on the other two, so 32 characters shows
# every input in full rather than a prefix of one.
BEST_INPUT_CHARS = 32


# Escaped one character at a time rather than by successive str.replace: the
# replacements themselves contain braces and backslashes, so a sequential pass
# escapes its own output and turns a single backslash into
# `\textbackslash\{\}`.
_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
}


def latex_escape(text: str) -> str:
    """Escapes a recovered input for typesetting inside \\texttt."""
    return "".join(_LATEX_ESCAPES.get(char, char) for char in text)


def tab_best_inputs(root: Path, cache: Path, arms: dict):
    """The highest-coverage input each PRG seed produced, per target.

    One row per seed rather than one per target. A single row shows what the
    best run converged on; four independent rows show whether the seeds
    converged on the *same* structure, which is the stronger claim and the one
    the structural-rate figures make over training. On cJSON the seeds are
    pooled across all fifteen arms, so the arm that produced each row is named
    -- the row is the best that PRG seed achieved anywhere in the campaign, not
    the best of a fixed arm.
    """
    lines = []
    for target, display in TARGETS.items():
        by_seed: dict[int, tuple[float, str, str, str]] = {}
        for (t, label), runs in sorted(arms.items()):
            if t != target:
                continue
            for run in runs:
                rows = load(cache, run, "best_inputs")
                if not rows:
                    continue
                # The extractor already ranks a run's inputs by score and then
                # by the executions they cost, so the first row is that run's
                # best under a tie-break that is recorded rather than incidental.
                top = rows[0]
                score = num(top, "coverage_score", 0.0)
                current = by_seed.get(run.seed)
                if current is None or score > current[0]:
                    by_seed[run.seed] = (score, label, top.get("seed_ascii", ""), top.get("source", ""))
        if not by_seed:
            continue
        if lines:
            lines.append(r"\addlinespace")
        for position, seed in enumerate(sorted(by_seed)):
            score, label, text, _ = by_seed[seed]
            lines.append(
                f"{display if position == 0 else ''} & {seed} & \\texttt{{{latex_escape(label)}}}"
                f" & {score:.0f} & \\texttt{{{latex_escape(text[:BEST_INPUT_CHARS])}}} \\\\"
            )
    body = f"""\\begin{{table}}[tbp]
  \\centering
  \\caption[Highest-coverage inputs]{{The highest-coverage input each PRG seed produced,
    rendered with non-printable bytes as dots. On cJSON the seed is taken across all fifteen
    arms and the arm that produced it is named; the other two campaigns have one arm each.
    All four cJSON seeds converge on a nested array and all four libxml2 seeds on nested tags,
    neither of which was described to the agent in any form, while picohttpparser shows no
    such agreement. These are the inputs behind the coverage numbers of
    \\cref{{fig:coverage-executions}}.}}
  \\label{{tab:best-inputs}}
  \\footnotesize
  \\begin{{tabular}}{{@{{}}lllrl@{{}}}}
    \\toprule
    Target & Seed & Arm & Blocks & Input \\\\
    \\midrule
{chr(10).join('    ' + line for line in lines)}
    \\bottomrule
  \\end{{tabular}}
\\end{{table}}
"""
    return write_tex(root, "tab-best-inputs", body)


FIGURES = {
    "coverage-executions": lambda root, cache, arms: fig_coverage(
        root, cache, arms, "executions_per_env", "coverage-executions",
        r"executions ($10^{3}$)", scale=1e-3,
        caption_axis="executions per environment",
    ),
    "coverage-wallclock": lambda root, cache, arms: fig_coverage(
        root, cache, arms, "wall_ms", "coverage-wallclock", "wall-clock hours",
        scale=1 / 3.6e6, caption_axis="wall-clock time",
    ),
    "input-learning": fig_input_learning,
    "input-losses": fig_input_losses,
    "input-entropy": fig_input_entropy,
    "structural-rate": fig_structural,
    "structural-decay": fig_structural_decay,
    "return": fig_return,
    "losses": fig_losses,
    "policy-improvement": fig_improvement,
    "collapse-entropy": fig_collapse,
    "depth-actions": fig_depth_actions,
    "ablation-strip": fig_ablation_strip,
    "saturation": fig_saturation,
    "tree-depth": fig_tree,
    "buffer-reward-density": fig_buffer,
    "tab-campaign-inventory": tab_campaign,
    "tab-deep-seed": tab_deep_seed,
    "tab-best-inputs": tab_best_inputs,
}


def build(root: Path, cache: Path, runs: list[Run], only: list[str] | None) -> list[Path]:
    arms = group_by_label(runs)
    written = []
    for name, builder in FIGURES.items():
        if only and name not in only:
            continue
        result = builder(root, cache, arms)
        if result:
            written.append(result)
    return written
