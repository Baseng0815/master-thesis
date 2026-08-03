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

**Current state:** every chapter under `sections/` is a skeleton — a heading plus a `% TODO` comment
describing what belongs there. The primary task in this repo is writing that content, grounded in the
companion code and the source papers. The document structure, packages, and bibliography are already
set up.

## The document class

The thesis uses **`sdqthesis.cls` v1.6**, the SDQ/KASTEL student-thesis template of the KIT
(<https://sdq.kastel.kit.edu/wiki/Dokumentvorlagen>); the upstream copy lives in
`~/abschlussarbeiten`. The class and its assets are vendored next to `thesis.tex`:

- `sdqthesis.cls` — the class. **Do not modify it**, and do not override the layout parameters it
  sets (font size, margins, line spacing, caption fonts, `\typearea`). A uniform layout across
  theses is the point of the template.
- `logos/` — KIT and SDQ logos for the title page.
- `title-background.pdf` — the KIT frame drawn behind the title page.

The class is based on **`scrbook`** (KOMA-Script), so KOMA idioms apply: `\frontmatter`/`\mainmatter`,
`parskip=half` (paragraphs are separated by vertical space, not indented), `\setkomafont`.

Class-specific commands used in `preamble.tex`: `\thesistype`, `\reviewerone`/`\reviewertwo`,
`\advisorone`/`\advisortwo`, `\editingtime`, `\location`, `\settitle`, `\setpdf`, and
`\includeabstract` (the last one from `thesis.tex`). **`\includeabstract` hard-codes the paths
`sections/abstract_en.tex` and `sections/abstract_de.tex`** — that is why the content directory is
called `sections/` and why the abstract is split in two files. A German abstract is mandatory for a
thesis written in English.

`draft` vs `final` is a `\documentclass` option (currently `draft`): `draft` shows `\todo` notes and
overfull-box markers, `final` hides them. Switch to `final` before submission — in `preamble.tex`,
which is the only place the class is loaded, so the chapter builds follow along. `preamble.tex` also
passes `final` to hyperref explicitly so that draft builds keep working PDF links.

## Building

The toolchain is provided via Nix (`latexmk`, `pdflatex`, `biber` are on the path).

```sh
make                        # build the whole thesis -> output/thesis.pdf
make chapters               # every chapter on its own -> output/chapters/*.pdf
make chapter-background     # just one of them
make list                   # the chapter names chapter-NAME accepts
make continuous             # rebuild the thesis on every save
make watch-background       # rebuild one chapter on every save
make clear                  # remove every generated file, PDFs included
```

Everything generated goes to `output/` (PDFs) and `output/aux/` (the `.aux`, `.log`, `.bcf`, …
clutter); `output/` is gitignored. A bare `latexmk -pdf thesis.tex` still works but writes next to
the sources.

The per-chapter PDFs exist to send a single chapter to an advisor for review. They are built by
`chapter.tex`, a second master document that shares `preamble.tex` and typesets one chapter with a
cover note; the Makefile passes the chapter file, its number and the path of the thesis `.aux` in on
the command line (`latexmk -usepretex`). Reading `thesis.aux` (via `xr`) is what keeps a chapter
excerpt honest: the chapter keeps its real number and a `\cref` into another chapter prints the
number that chapter has in the full thesis instead of `??`. Page numbers, citation numbers and the
bibliography are necessarily local to the excerpt. `make chapters` therefore builds the thesis first.

The bibliography backend is **biber** (not bibtex) — biblatex is configured with
`backend=biber`. `latexmk` invokes it automatically; a manual sequence would be
`pdflatex → biber → pdflatex → pdflatex`. There is no `latexmkrc`.

## Document structure

Three files at the top level carry the document itself:

- `preamble.tex` — class options, thesis metadata, the packages the class does not already load, and
  the theorem environments. Both master documents `\input` it as their first line, so the class is
  loaded in exactly one place.
- `thesis.tex` — the complete thesis: front matter, then one `\input` per chapter, then the
  bibliography and appendix. It defines the document order and nothing else.
- `chapter.tex` — the review-copy master, one chapter per PDF; never built by hand, see
  [Building](#building).

Content lives in `sections/`, one file per section or chapter, mirroring the outline:

- **Front matter** — `sections/{declaration,abstract_en,abstract_de}.tex`
- **Introduction** — `sections/introduction.tex`
- **Background** — `sections/background/{fuzzing,reinforcement-learning}.tex`
- **EfficientZero** — `sections/efficientzero.tex` (the algorithm)
- **Related Work** — `sections/related-work.tex`
- **Platform / MDP formulation** — `sections/{platform,fuzzing-mdp}.tex`
- **Action spaces** — `sections/fuzzing-input-actions/` and `sections/fuzzing-corpus-actions/`
  (the two chapters share a section order and are meant to be read as a diff)
- **Implementation** — `sections/implementation.tex`
- **Targets** — `sections/targets/*.tex` (evaluation targets, from microbenchmark to real-world)
- **Methodology / Results** — `sections/methodology.tex`, `sections/results/*.tex`
- **Failure modes / Discussion** — `sections/failure-modes.tex`, `sections/discussion/*.tex`
- **Conclusion / Future Work / Appendix** —
  `sections/{conclusion,future-work,appendix}.tex`

To reorder, add, or remove a chapter, edit the `\input` lines in `thesis.tex` — it is the single
source of truth for document order, and `make chapters` derives its chapter list from those lines
(every `\input{sections/...}` after `\mainmatter`, in order, is one chapter; the ones after
`\appendix` are appendix chapters).

**One chapter is always one file under `sections/`.** A chapter split over several section files
gets a wrapper file that holds the `\chapter` heading and `\input`s the sections —
`sections/background.tex`, `sections/fuzzing-{input,corpus}-actions.tex`, `sections/targets.tex`,
`sections/results.tex`, `sections/discussion.tex`. Nothing but chapter-level `\input` lines belongs
in `thesis.tex`; a `\chapter` or `\section` heading written there would be invisible to the chapter
builds.

Conventions to match when editing chapter files:

- Each chapter file starts with a `%!TEX root = ...` magic comment pointing at `thesis.tex` (relative
  depth varies: `../thesis.tex` for top-level chapters, `../../thesis.tex` for nested sections).
- `\input` paths are always written from the repository root (`\input{sections/targets/cjson}`), not
  relative to the including file — both master documents are built from the root.
- Section/chapter files use `\section`/`\chapter` with a `\label` following the existing scheme
  (`sec:...`, `chap:...`, e.g. `\label{sec:target-open62541}`).
- Cross-reference with **cleveref** (`\cref{...}`, `\Cref{...}`) — it is loaded `capitalise,noabbrev`,
  so write `\cref{chap:efficientzero}`, not a hand-typed "Chapter 2".
- Cite with biblatex numeric style: `\cite{ye_mastering_2021}`. Bib entries live in
  `references/fuzzing.bib` and `references/reinforcement-learning.bib`
  (biber format, exported from Zotero — do not hand-edit; Bastian adds entries via Zotero).
  During drafting, `\nocite{*}` in `thesis.tex` can list every bib entry.
- Figures go in `figures/`, one TikZ picture per file, `\input` from the chapter that discusses it;
  `\graphicspath{{figures/}}` is set, so reference images by bare filename.
- `\todo{...}` uses `\marginpar`, so it must not appear inside a float, `minipage` or `subfigure` —
  LaTeX aborts with "Float(s) lost". Put the note in the surrounding text instead.

Available machinery from `preamble.tex` (already loaded — use rather than re-adding packages): `amsmath`/
`mathtools` and theorem environments (`theorem`, `lemma`, `corollary`, `definition`, `example`);
`algorithm`/`algpseudocode` for pseudocode; `listings` (`lstlisting`, styled) for source; `siunitx`
for numbers/units; `booktabs`/`tabularx` for tables; `subcaption` for subfigures; `tikz` for
diagrams. The class itself adds `booktabs`, `longtable`, `array`, `enumitem`, `graphicx`, `url`,
`hyperref` and `csquotes`, plus `\code{...}` and `\model{...}` text macros. Draft aids: `todonotes`
provides `\todo{...}` and `\listoftodos` (the list is commented out in `thesis.tex`).

`amssymb` is deliberately *not* loaded: the class pulls in `newtxmath`, which provides `\mathbb` and
`\mathcal` already and clashes with `amssymb`.

Outstanding TODOs in `preamble.tex`: examiners, advisors, editing period and location — all marked
`TODO:` so they show up on the title and declaration pages until filled in.

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
