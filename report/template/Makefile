all:
	# -shell escape : nécessaire pour minted
	pdflatex -shell-escape report.tex
	# on compile une deuxième fois pour les références
	pdflatex -shell-escape report.tex

clean:
	rm -rf *bak *~ *out *log *aux _minted-report *.aex

run:
	pdflatex -shell-escape rapport-gbaguidi-lengrai.tex
	pdflatex -shell-escape rapport-gbaguidi-lengrai.tex
