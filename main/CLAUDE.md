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

## The template

The thesis uses the **institute thesis template of the Fraunhofer IOSB / KIT IES**, whose upstream
copy lives in `~/latex-template-thesis`
(`gitlab.cc-asp.fraunhofer.de:fuzzing/student-work/theses/latex-template-thesis`). There is no
document class: the template is a plain **`scrbook`** (KOMA-Script) setup plus a set of preamble
files, all vendored next to `thesis.tex`:

- `preamble/01-fonts.tex` … `05-math.tex` — the template's own preamble files. **Keep them as close
  to upstream as possible** so they stay diffable against `~/latex-template-thesis`; anything this
  thesis needs on top goes in `preamble/06-thesis.tex`. Do not override the layout parameters they
  set (font size, `BCOR`/`DIV`, line spacing, page head) — a uniform layout across the institute's
  theses is the point of the template.
- `preamble-final-setup.tex` — everything that has to run after the metadata: `\hypersetup`, theorem
  environments, cleveref names, the `listings` style, `\makeindex`/`\makeglossaries` and the
  `\addbibresource` lines.
- `KAcolors.sty` — the KIT corporate colors (`KITblue`, `KITred`, … , `KITblack50`), used by the
  title page and by the `pgfplots` styles in `preamble/03-graphics.tex`.
- `logos/` — KIT, Fraunhofer IOSB and IES logos for the title page.

Every place where this thesis departs from the upstream template is marked with a `DEVIATION`
comment. The deviations are: English instead of German as the main language (and no `icomma`),
`subcaption` instead of the unmaintained `subfig`, numeric instead of alphabetic citations, Rust
instead of Java in the `listings` setup, and several `\addbibresource` lines instead of one
`literature.bib`.

Since the template is `scrbook`, KOMA idioms apply: `\frontmatter`/`\mainmatter`/`\backmatter`,
`\addchap`/`\addsec`, `\setkomafont`. Note that unlike the previous template (SDQ/KASTEL) this one
does **not** set `parskip` — paragraphs are indented, not separated by vertical space.

The title page (`sections/titlepage.tex`) and the declaration (`sections/declaration.tex`) are
ordinary content files that read the metadata macros defined in `preamble.tex`: `\worktitle`,
`\typeofthesis`, `\nameofauthor`, `\placeofexam`, `\dateofexam`, `\editingstart`/`\editingend`,
`\reviewer`, `\advisorA`/`\advisorB` (leave `\advisorB` empty and the line is dropped). A German
abstract is mandatory for a thesis written in English, which is why the abstract is split into
`sections/abstract_en.tex` and `sections/abstract_de.tex`.

Draft vs. final is the `\ifthesisdraft` boolean at the top of `preamble.tex`: it drives both the
class's overfull-box markers and the mode `todonotes` is loaded in. Set it to `\thesisdraftfalse`
before submission — `preamble.tex` is the only place the class is loaded, so the chapter builds
follow along. The template passes `final` to `graphicx`, `listings`, `microtype`, `hyperref` and
`scrlayer-scrpage` explicitly, so draft builds keep their graphics and working PDF links.

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
`pdflatex → biber → pdflatex → pdflatex`.

`latexmkrc` teaches `latexmk` the two custom dependencies that build the glossary (`.glo → .gls`)
and the acronym list (`.acn → .acr`) with `makeindex`. The `glossaries` package could do this
itself with its `automake` option, but only through `\write18`, which would mean building with
`-shell-escape`. The index (`.idx → .ind`) and biber need no help. **A `make continuous` that was
started before `latexmkrc` changed does not see the change** — restart it, otherwise the acronym
list silently stays stale.

## Document structure

Three files at the top level carry the document itself:

- `preamble.tex` — the draft/final switch, the class options, the `\input`s of `preamble/*` and
  `preamble-final-setup.tex`, and the thesis metadata. Both master documents `\input` it as their
  first line, so the class is loaded in exactly one place.
- `thesis.tex` — the complete thesis: front matter, then one `\input` per chapter, then the
  appendix and the back matter. It defines the document order and nothing else.
- `chapter.tex` — the review-copy master, one chapter per PDF; never built by hand, see
  [Building](#building).

Content lives in `sections/`, one file per section or chapter, mirroring the outline:

- **Front matter** — `sections/{titlepage,declaration,abstract_en,abstract_de,notation}.tex`
- **Back matter** — `sections/backmatter.tex` (bibliography, lists of figures/tables/theorems/
  listings, acronyms, index) and `sections/acronyms.tex` (the `\newacronym` definitions, `\input`
  from `preamble.tex` because they have to run in the preamble)
- **Introduction** — `sections/introduction.tex`
- **Background** — `sections/background/{fuzzing,reinforcement-learning}.tex`
- **EfficientZero** — `sections/efficientzero.tex` (the algorithm)
- **Related Work** — `sections/related-work.tex`
- **MDP formulation / action spaces** — `sections/fuzzing-mdp.tex` and `sections/fuzzing-mdp/`.
  One chapter, and the thesis's design chapter: three shared sections (`interface`,
  `constraints`, `design-space`), then the two action-space formulations as parallel sections
  (`input-actions.tex` and `corpus-actions.tex`, each `\input`ing five `input-*`/`corpus-*`
  subsection files in the same order), then one shared `prior-work.tex`. **The `input-*` and
  `corpus-*` files are meant to be read as a diff — keep the two sets aligned, same headings in
  the same order, when editing either.**
- **Architecture / Implementation** — `sections/implementation.tex` and `sections/implementation/`.
  `architecture.tex` is the whole-system overview (`fig:system-architecture`); `platform.tex`
  describes MOGI as one layer of it (`fig:platform-architecture`); the rest is the software
  written for this thesis. MOGI has no chapter of its own — introduce it in its role, not as a
  standalone tour.
- **Targets** — `sections/targets/*.tex` (evaluation targets, from microbenchmark to real-world)
- **Methodology / Results** — `sections/methodology.tex`, `sections/results/*.tex`
- **Failure modes / Discussion** — `sections/failure-modes.tex`, `sections/discussion/*.tex`
- **Conclusion / Future Work / Appendix** —
  `sections/{conclusion,future-work,appendix}.tex`

To reorder, add, or remove a chapter, edit the `\input` lines in `thesis.tex` — it is the single
source of truth for document order, and `make chapters` derives its chapter list from those lines
(every `\input{sections/...}` between `\mainmatter` and `\backmatter`, in order, is one chapter; the
ones after `\appendix` are appendix chapters; what follows `\backmatter` is not a chapter).

**One chapter is always one file under `sections/`.** A chapter split over several section files
gets a wrapper file that holds the `\chapter` heading and `\input`s the sections —
`sections/background.tex`, `sections/fuzzing-mdp.tex`, `sections/implementation.tex`,
`sections/targets.tex`, `sections/results.tex`, `sections/discussion.tex`. A section that is
itself split (the two action-space formulations, the platform) gets the same treatment one level
down. Nothing but chapter-level `\input` lines belongs
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
  During drafting, `\nocite{*}` in `preamble-final-setup.tex` can list every bib entry.
- Figures go in `figures/`, one TikZ picture per file, `\input` from the chapter that discusses it;
  `\graphicspath{{figures/}}` is set, so reference images by bare filename.
- `\todo{...}` uses `\marginpar`, so it must not appear inside a float, `minipage` or `subfigure` —
  LaTeX aborts with "Float(s) lost". Put the note in the surrounding text instead.
- Acronyms are defined in `sections/acronyms.tex` and used with `\gls{mcts}` (long at first use,
  short afterwards), `\glspl{}` for the plural, `\acrlong{}`/`\acrshort{}` to force one form. An
  acronym that is never used still appears in the list — `sections/backmatter.tex` calls
  `\glsaddallunused`. Most of the existing text still spells acronyms out by hand; converting it is
  ongoing work, not a rule to enforce retroactively in unrelated edits.
- Index entries are written as `\index{term}` (`\index{term!subterm}` for a subentry) at the point
  where a term is *defined*, not at every mention. Only a seed set exists so far, in the two
  background chapters.
- `sections/notation.tex` lists the symbols the thesis uses; keep it in sync when a chapter
  introduces new notation.

Available machinery from `preamble.tex` (already loaded — use rather than re-adding packages):
`amsmath`/`amssymb`/`mathtools`/`mathdots`/`xfrac` and the `ntheorem` environments (`theorem`,
`lemma`, `corollary`, `proposition`, `definition`, `example`); the template's own math macros in
`preamble/05-math.tex` (`\argmin`/`\argmax`, `\E`, `\Var`, `\Tr`, `\diff`, `\dsR`/`\dsN`, …);
`algorithm`/`algpseudocode` for pseudocode; `listings` (`lstlisting`, plus `latex`, `rust` and
`ccode` environments) for source; `siunitx` for numbers/units; `booktabs`/`tabularx`/`tabulary`/
`multirow`/`ltxtable` for tables; `subcaption` for subfigures; `tikz` and `pgfplots` (with `KIT …
plot` styles and the `KAcolors` palette) for diagrams; `enumitem` for lists; `glossaries` for
acronyms; `\code{...}` and `\model{...}` for identifiers and model names in text. Draft aids:
`todonotes` provides `\todo{...}` and `\listoftodos` (the list is commented out in `thesis.tex`).

Unlike under the previous template, `amssymb` *is* loaded — `preamble/01-fonts.tex` loads it before
`newtxmath`, which is the order that works.

Metadata to re-check in `preamble.tex` before submission: `\dateofexam` is the end of the editing
period (13 August 2026), which is the submission date, not necessarily the date of the colloquium.
The template's title page has a single `\reviewer` field where the previous one had a first and a
second examiner, so only the first examiner is printed; `\advisorB` is empty because there is one
advisor.

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
  binaries running under emulation. This is the source for the *Fuzzing as a Markov Decision
  Process*, *System Architecture and Implementation*, *Targets*, and *Results* chapters. Key pieces
  to read when writing those chapters:
  - A fuzzing target is an `efficientzero` `Environment` (traits `Environment`/`Action`/
    `Observation`/`StepResult` from `efficientzero::abstraction`). `step` feeds an action into the
    emulated program and runs it; `reset` restores an emulator snapshot. See `mugiwara/examples/`
    (`two_state.rs`, `high-and-low.rs`, `exit.rs`) for worked target implementations — these are the
    toy targets the thesis's *Targets* chapter describes.
  - `mugiwara/src/instrument/` (`BlockHitTracker`) computes the **coverage signal**: basic-block hit
    addresses are FNV-hashed into a fixed bucket array, giving the reward/observation vector. This is
    the concrete "coverage feedback" behind `sec:platform-coverage`.
  - `mugiwara/src/lib.rs` builds and snapshots the emulator (`build_emulator`/`setup_emulator`,
    `EmulatorArgs`) — the MOGI experimental setup, described in `sections/implementation/platform.tex`.

When you need a fact about the implementation that isn't in this repo, read the companion source or
its `CLAUDE.md`/`guidelines/` rather than inferring it from the thesis prose (which may still be a
stub).
