#!/usr/bin/env bash
set -euo pipefail

MAIN="1-prop-logic"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR"

rm -f \
	"$MAIN.aux" \
	"$MAIN.log" \
	"$MAIN.nav" \
	"$MAIN.out" \
	"$MAIN.snm" \
	"$MAIN.toc" \
	"$MAIN.vrb" \
	"$MAIN.xdv" \
	"$MAIN.synctex.gz"

xelatex "$MAIN.tex"
xelatex "$MAIN.tex"