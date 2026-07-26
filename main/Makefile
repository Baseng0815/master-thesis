# ============================================================================
# Thesis build. The toolchain (latexmk, pdflatex, biber) is provided by Nix.
#
#   make             build thesis.pdf once
#   make continuous  rebuild on every save, without opening a previewer
#   make clear       remove every generated file, thesis.pdf included
#
# latexmk decides by itself how many pdflatex passes are needed and when to run
# biber, so there is no manual pdflatex -> biber -> pdflatex sequence here.
# ============================================================================

MAIN    := thesis
LATEXMK := latexmk

# -pdf              produce PDF via pdflatex (biber is driven from the .bcf)
# -interaction=...  never stop for keyboard input on an error
# -file-line-error  report errors as file:line:message, so editors can jump
FLAGS   := -pdf -interaction=nonstopmode -file-line-error

.PHONY: all continuous clear clean

all:
	$(LATEXMK) $(FLAGS) $(MAIN).tex

# -pvc      keep running, rebuild whenever a source file changes
# -view=none suppress the previewer that -pvc would otherwise launch
continuous:
	$(LATEXMK) $(FLAGS) -pvc -view=none $(MAIN).tex

# -C removes all generated files including the PDF (-c would keep it).
# The *-SAVE-ERROR files are left behind by failed biber runs; latexmk does not
# know about them, so they are removed explicitly.
clear:
	$(LATEXMK) -C $(MAIN).tex
	$(RM) $(MAIN).bbl-SAVE-ERROR $(MAIN).bcf-SAVE-ERROR

# Convenience alias, for muscle memory.
clean: clear
