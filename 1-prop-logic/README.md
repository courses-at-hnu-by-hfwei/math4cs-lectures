# 1-prop-logic

Lecture slides for propositional logic.

The main source file is `1-prop-logic.tex`, a Beamer deck titled `1-prop-logic: 命题逻辑 (Propositional Logic)`.

## Contents

- `1-prop-logic.tex`: main entry point
- `parts/`: slide content split by topic
- `tables/`: tabular material used by the slides
- `figs/`: figures used by the deck
- `refs/`: reference material
- `build-win.bat`: Windows build script
- `build-linux.sh`: Linux build script
- `build-macos.sh`: macOS build script

## Topics

The deck currently includes:

- introduction
- propositional logic syntax
- propositional logic semantics
- propositional logic inference
- closing suggestion slide

## Requirements

To compile this lecture, install a TeX distribution with at least:

- `xelatex`
- Beamer and the packages used by the shared lecture preamble

This lecture also depends on the shared preamble file at `../preamble.tex`.

## Build

### Windows

Run:

```bat
build-win.bat
```

### Linux

Run:

```bash
chmod +x build-linux.sh
./build-linux.sh
```

### macOS

Run:

```bash
chmod +x build-macos.sh
./build-macos.sh
```

## Manual Build

If you prefer to compile manually from this directory:

```bash
xelatex 1-prop-logic.tex
xelatex 1-prop-logic.tex
```

Running XeLaTeX twice resolves Beamer navigation and table-of-contents related auxiliary files.

## Output

The generated PDF is:

- `1-prop-logic.pdf`

Auxiliary files such as `.aux`, `.log`, `.nav`, `.out`, `.snm`, `.toc`, and `.vrb` are produced during compilation.