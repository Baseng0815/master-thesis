# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is the **LaTeX source of Bastian Engel's master's thesis**, "Applications
of Reinforcement Learning to Stateful Emulator-Based Greybox Fuzzing". It is a
writing project, not a code project: it contains prose, figures, and a
bibliography that compile to `thesis.pdf`. The actual implementation lives in
two companion repositories (see [Companion
repositories](#companion-repositories)) — this repo *describes and evaluates*
that work.

The thesis studies **emulator-based stateful greybox fuzzing driven by EfficientZero**, a
sample-efficient model-based reinforcement-learning algorithm. Fuzzing is framed as an RL problem:
the target program under emulation is the environment, mutations/protocol actions are the action
space, and coverage feedback (basic-block hit counts) is the reward and observation signal.

**Current state:** every chapter under `chapters/` is a skeleton — a heading plus a `% TODO` comment
describing what belongs there. The primary task in this repo is writing that content, grounded in the
companion code and the source papers. The document structure, packages, and bibliography are already
set up.

## Building

The toolchain is provided via Nix (`latexmk`, `pdflatex`, `biber` are on the path).

```sh
latexmk -pdf thesis.tex     # full build; runs pdflatex + biber as needed
latexmk -pvc thesis.tex     # continuous preview: rebuild on save
latexmk -C                  # clean all generated files (aux, bbl, pdf, ...)
```

The bibliography backend is **biber** (not bibtex) — biblatex is configured with
`backend=biber`. `latexmk` invokes it automatically; a manual sequence would be
`pdflatex → biber → pdflatex → pdflatex`. There is no `latexmkrc` or `Makefile`.

## Document structure

`thesis.tex` is the master document: it holds the preamble (packages, theorem environments,
metadata) and `\input`s each chapter. Content lives in `chapters/`, one file per section or chapter,
mirroring the outline:

- **Introduction** — `chapters/introduction/{fuzzing,reinforcement-learning,reinforcement-fuzzing}.tex`
- **EfficientZero** — `chapters/efficientzero.tex` (the algorithm)
- **Fuzzing with EfficientZero** — `chapters/efficientzero-fuzzing.tex` (how the algorithm is applied: state/action/reward design)
- **Targets** — `chapters/targets/{bandit,contextual-bandit,sequence,open62541}.tex` (evaluation targets, from toy to real-world)
- **MOGI Setup** — `chapters/mogi-setup.tex` (the emulator/experiment harness)
- **Analysis** — `chapters/analysis/{challenge,evaluation,advantages,disadvantages}.tex`
- **Conclusion / Future Work** — `chapters/{conclusion,future-work}.tex`

To reorder, add, or remove a chapter, edit the `\input` lines in `thesis.tex` — it is the single
source of truth for document order. `chapters/abstract.tex` is `\input` before the table of contents.

Conventions to match when editing chapter files:

- Each chapter file starts with a `%!TEX root = ...` magic comment pointing at `thesis.tex` (relative
  depth varies: `../thesis.tex` for top-level chapters, `../../thesis.tex` for nested sections).
- Section/chapter files use `\section`/`\chapter` with a `\label` following the existing scheme
  (`sec:...`, `chap:...`, e.g. `\label{sec:target-open62541}`).
- Cross-reference with **cleveref** (`\cref{...}`, `\Cref{...}`) — it is loaded `capitalise,noabbrev`,
  so write `\cref{chap:efficientzero}`, not a hand-typed "Chapter 2".
- Cite with biblatex numeric style: `\cite{ye_mastering_2021}`. Bib entries live in
  `references/fuzzing.bib`, `references/reinforcement-learning.bib`, and `references/misc.bib`
  (biber format, exported from Zotero — do not hand-edit; Bastian adds entries via Zotero).
  During drafting, `\nocite{*}` in `thesis.tex` can list every bib entry.
- Figures go in `figures/` (currently empty); `\graphicspath{{figures/}}` is set, so reference images
  by bare filename.

Available preamble machinery (already loaded — use rather than re-adding packages): `amsmath`/
`mathtools` and theorem environments (`theorem`, `lemma`, `corollary`, `definition`, `example`);
`algorithm`/`algpseudocode` for pseudocode; `listings` (`lstlisting`, styled) for source; `siunitx`
for numbers/units; `booktabs`/`tabularx` for tables; `subcaption` for subfigures. Draft aids:
`todonotes` provides `\todo{...}` and `\listoftodos` (the list is commented out in `thesis.tex`).

Outstanding preamble TODOs: final title (appears twice — metadata and titlepage), and titlepage
university/faculty/supervisors/submission date.

## Companion repositories

The technical claims, figures, and results in this thesis come from two sibling Rust repos. Treat
them as the ground truth for anything about *how the system works* — read the code before describing
its behavior, and keep the prose consistent with what the code actually does.

- **`~/efficientzero`** — a generic, reusable Rust implementation of EfficientZero (a sample-efficient
  MuZero variant) built on the `burn` deep-learning framework. Its own `CLAUDE.md` maps the modules
  (`model`, `mcts`, `learner`, `driver`, `abstraction`). This is the source for the
  *EfficientZero* chapter.
  - **`~/efficientzero/guidelines/`** holds the primary papers as PDFs: `efficientzero.pdf`,
    `muzero.pdf`, `prioritized-experience-replay.pdf`, plus a reference implementation under
    `guidelines/efficientzero/`. Cite and summarize from these for the algorithm chapters.

- **`~/mugiwara`** — the RL-driven fuzzer. It combines `efficientzero` with the **Mogi Emulator
  Framework** (`~/fuzzyemu`: `mogi_emulator`, `mogi_fuzzer`, `mogi_unicorn`, `mogi_system`) to fuzz
  binaries running under emulation. This is the source for the *Fuzzing with EfficientZero*, *MOGI
  Setup*, *Targets*, and *Analysis* chapters. Key pieces to read when writing those chapters:
  - A fuzzing target is an `efficientzero` `Environment` (traits `Environment`/`Action`/
    `Observation`/`StepResult` from `efficientzero::abstraction`). `step` feeds an action into the
    emulated program and runs it; `reset` restores an emulator snapshot. See `mugiwara/examples/`
    (`two_state.rs`, `high-and-low.rs`, `exit.rs`) for worked target implementations — these are the
    toy targets the thesis's *Targets* chapter describes.
  - `mugiwara/src/instrument/` (`BlockHitTracker`) computes the **coverage signal**: basic-block hit
    addresses are FNV-hashed into a fixed bucket array, giving the reward/observation vector. This is
    the concrete "coverage feedback" the *Fuzzing with EfficientZero* chapter should explain.
  - `mugiwara/src/lib.rs` builds and snapshots the emulator (`build_emulator`/`setup_emulator`,
    `EmulatorArgs`) — the MOGI experimental setup.

When you need a fact about the implementation that isn't in this repo, read the companion source or
its `CLAUDE.md`/`guidelines/` rather than inferring it from the thesis prose (which may still be a
stub).
