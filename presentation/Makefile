# Defense presentation. Figures/ and KAcolors.sty are symlinks into ../main.
LATEXMK = latexmk -pdf -interaction=nonstopmode -outdir=build

all: build/main.pdf

build/main.pdf: main.tex
	$(LATEXMK) main.tex

watch:
	$(LATEXMK) -pvc main.tex

clean:
	latexmk -C -outdir=build

.PHONY: all watch clean
