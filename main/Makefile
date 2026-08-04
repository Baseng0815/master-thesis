# ============================================================================
# Thesis build. The toolchain (latexmk, pdflatex, biber) is provided by Nix.
#
#   make                build the whole thesis -> output/thesis.pdf
#   make chapters       build every chapter on its own -> output/chapters/*.pdf
#   make chapter-NAME   build a single chapter, e.g. make chapter-background
#   make list           show the chapter names that NAME can be
#   make continuous     rebuild the thesis on every save
#   make watch-NAME     rebuild one chapter on every save
#   make clear          remove every generated file, PDFs included
#
# The per-chapter PDFs are review copies to be sent out one at a time; see
# chapter.tex for what they do and do not preserve of the full document.
#
# latexmk decides by itself how many pdflatex passes are needed and when to run
# biber, so there is no manual pdflatex -> biber -> pdflatex sequence here. It
# also does its own dependency checking, which is why the build targets below
# are unconditional: make only decides whether to ask latexmk, latexmk decides
# whether anything actually has to be rerun.
# ============================================================================

MAIN    := thesis
LATEXMK := latexmk

# Nothing generated is written next to the sources: the PDFs land in output/
# and output/chapters/, all the aux clutter (.aux, .log, .bcf, .fdb_latexmk,
# ...) in output/aux/. output/ is gitignored, which keeps `git status' readable
# and makes `make clear' a single rm.
OUTDIR  := output
AUXDIR  := $(OUTDIR)/aux
CHAPDIR := $(OUTDIR)/chapters

# -pdf              produce PDF via pdflatex (biber is driven from the .bcf)
# -interaction=...  never stop for keyboard input on an error
# -file-line-error  report errors as file:line:message, so editors can jump
# -auxdir           keep the intermediate files out of the PDF directories;
#                   the thesis and the chapters can share it because each build
#                   runs under its own -jobname
FLAGS   := -pdf -interaction=nonstopmode -file-line-error -auxdir=$(AUXDIR)

# ----------------------------------------------------------------------------
# The chapter list is read out of thesis.tex so that it cannot drift from the
# document: every \input{sections/...} between \mainmatter and \backmatter is
# one chapter, and its position in that list is the chapter number the review
# build has to print. Files inputted after \appendix are appendix chapters,
# which LaTeX letters by itself, so their number is not used. What follows
# \backmatter is the bibliography and the lists, not a chapter to review.
# Each entry is name:number:kind.
# ----------------------------------------------------------------------------
CHAPTER_SPECS := $(shell awk ' \
	/^\\mainmatter/ { body = 1; next } \
	/^\\backmatter/ { body = 0; next } \
	/^\\appendix/   { kind = "appendix" } \
	body && /^\\input\{sections\// { \
		name = $$0; \
		sub(/^\\input\{sections\//, "", name); \
		sub(/\}.*$$/, "", name); \
		if (kind == "appendix") print name ":0:appendix"; \
		else { n++; print name ":" n ":chapter" } \
	}' $(MAIN).tex)

CHAPTERS     := $(foreach s,$(CHAPTER_SPECS),$(firstword $(subst :, ,$(s))))
CHAPTER_PDFS := $(patsubst %,$(CHAPDIR)/%.pdf,$(CHAPTERS))

# Fields of the entry belonging to chapter $(1).
chapter_num  = $(word 2,$(subst :, ,$(filter $(1):%,$(CHAPTER_SPECS))))
chapter_kind = $(word 3,$(subst :, ,$(filter $(1):%,$(CHAPTER_SPECS))))

# What chapter.tex needs to know about the chapter it is about to typeset,
# handed to pdflatex ahead of the file itself (latexmk's -usepretex).
pretex = \def\ChapterFile{sections/$(1)}\def\ChapterNumber{$(call chapter_num,$(1))}\def\ChapterKind{$(call chapter_kind,$(1))}\def\ThesisAux{$(AUXDIR)/$(MAIN)}

# Refuse an unknown name instead of handing pdflatex an empty chapter number.
define require_chapter
@test -n '$(call chapter_kind,$(1))' || \
	{ echo "make: no chapter '$(1)' in $(MAIN).tex --- run 'make list'" >&2; exit 1; }
@test -f $(AUXDIR)/$(MAIN).aux || \
	{ echo "make: $(AUXDIR)/$(MAIN).aux is missing --- run 'make' once first" >&2; exit 1; }
endef

# `make continuous' leaves a latexmk running on the thesis. A second latexmk with
# the same jobname and aux directory writes thesis.aux and thesis.bcf underneath
# it, which corrupts both builds --- so every target that would start one asks
# first whether the watcher is already there. The watcher keeps thesis.aux
# current by itself, which is all a chapter build needs from it. The bracket in
# the pattern keeps pgrep from matching the shell that runs it.
WATCHING := $(shell pgrep -f -- '-pvc.*[t]hesis\.tex' >/dev/null 2>&1 && echo 1)

.PHONY: all chapters list continuous clear clean FORCE

all: $(OUTDIR)/$(MAIN).pdf

chapters: $(CHAPTER_PDFS)

list:
	@printf '%s\n' $(CHAPTERS)

$(OUTDIR)/$(MAIN).pdf: FORCE
ifeq ($(WATCHING),1)
	@echo "make: 'make continuous' is rebuilding $(MAIN).pdf in another terminal, using its output"
else
	$(LATEXMK) $(FLAGS) -outdir=$(OUTDIR) $(MAIN).tex
endif

# A chapter build reads the thesis .aux to resolve references into the rest of
# the document, so the thesis is always built first.
$(CHAPDIR)/%.pdf: $(OUTDIR)/$(MAIN).pdf FORCE
	$(call require_chapter,$*)
	$(LATEXMK) $(FLAGS) -outdir=$(CHAPDIR) -jobname=$* \
		-usepretex='$(call pretex,$*)' chapter.tex

chapter-%: $(CHAPDIR)/%.pdf
	@:

# -pvc      keep running, rebuild whenever a source file changes
# -view=none suppress the previewer that -pvc would otherwise launch
continuous:
ifeq ($(WATCHING),1)
	@echo "make: a continuous build of $(MAIN).tex is already running --- not starting a second one" >&2
	@false
else
	$(LATEXMK) $(FLAGS) -outdir=$(OUTDIR) -pvc -view=none $(MAIN).tex
endif

watch-%: $(OUTDIR)/$(MAIN).pdf
	$(call require_chapter,$*)
	$(LATEXMK) $(FLAGS) -outdir=$(CHAPDIR) -jobname=$* \
		-usepretex='$(call pretex,$*)' -pvc -view=none chapter.tex

# Dropping output/ is enough for anything built by the rules above. The second
# and third line clean up after builds that wrote next to thesis.tex: earlier
# versions of this Makefile did, and a bare `latexmk thesis.tex' still does.
# -C removes all generated files including the PDF (-c would keep it); it is
# prefixed with `-' because latexmk reports a failure when the leftovers it is
# asked to clean up are the leftovers of a failed run, which is not a reason to
# stop cleaning. latexmk spares .bbl files (they may be hand-written; ours are
# not) and does not know about the *-SAVE-ERROR files that failed biber runs
# leave behind, so both go in the last line.
clear:
	$(RM) -r $(OUTDIR)
	-$(LATEXMK) -C $(MAIN).tex
	$(RM) $(MAIN).bbl $(MAIN).bbl-SAVE-ERROR $(MAIN).bcf-SAVE-ERROR

# Convenience alias, for muscle memory.
clean: clear

# Order the build targets on latexmk's judgement rather than make's.
FORCE:
