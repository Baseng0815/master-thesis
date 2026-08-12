# Writing Guidelines

How to write the thesis prose. Read before writing or editing anything under
`sections/`. LaTeX mechanics — cross-references, citations, acronyms, figures,
labels — are in [`CLAUDE.md`](../CLAUDE.md#document-structure); this file is about
the text itself.

## Match the surrounding prose

Read the neighboring sections before adding to a chapter, and write in the voice
they already use:

- **One sentence per line.** Every written file follows it, and it keeps a diff
  per-sentence instead of per-paragraph. Never reflow a paragraph you did not
  otherwise change.
- **Present tense.** `we` for what this thesis does ("We implement our fuzzer on
  top of the MOGI emulation framework"), plain third person for prior work
  ("MuZero removes the dependency on the simulator").
- **Reuse the thesis's own terms.** A concept named in `sections/notation.tex`,
  `sections/acronyms.tex` or an earlier chapter keeps that name; a synonym
  introduced later reads as a second concept.
- **One idea per paragraph.** Paragraphs are indented, not spaced, so a paragraph
  break is the only visible unit of thought.

`sections/efficientzero.tex` §"From AlphaGo to EfficientZero" is the house
example: one paragraph per system, opening with the system and its citation,
closing with what it achieved.

## One subject per section

A section about X contains only what is true of X. Pulling in Y — an alternative
design, a predecessor, the other action space — moves Y's responsibility into X's
section, and the reader has to separate the two again.

The parallel `input-*` and `corpus-*` files in `sections/fuzzing-mdp/` are where
this matters most: each describes its own action space and nothing about the
other. Their comparison belongs to the shared sections of that chapter.

Three ways to keep a section clean:

- **`\cref` the section that owns the topic** instead of re-explaining it. That is
  what cleveref is for, and the explanation stays in one place.
- **Give the comparison its own section**, whose subject *is* the difference.
- **Keep a one-clause contrast** only where a reader would otherwise carry an
  assumption over from the thing not being described.

Background chapters define what later chapters use, not the other way round: do
not pre-empt a design decision in the chapter that only supplies its vocabulary.

## Information density

Every sentence carries a fact the reader does not already have.

- **Open with the claim**, not with what the section is about to do. No "This
  section describes…", no "In the following, we first…". The table of contents and
  `\cref` already do the signposting.
- **Numbers over adjectives.** "\SI{194.3}{\percent} mean human performance" beats
  "performed remarkably well". In the results chapters every number names the
  measurement it comes from.
- **Say it once.** No paragraph restating the section at its end, no list
  re-listing what a table already holds.
- **Cut hedging that carries no information** — "it seems", "arguably", "it is
  worth noting". State real uncertainty with its cause: what went unmeasured, how
  many seeds a result rests on.
- **One example per point.** A second earns its place only by covering a case the
  first does not.
- **No filler vocabulary** — `leverage`, `utilize`, `seamlessly`, `robustly`,
  `delve`, `it is important to note`. They read as machine-written.

Length is a consequence of the content, not a target: say what the reader needs,
then stop.
