@echo off
setlocal

set "MAIN=1-prop-logic"

pushd "%~dp0"

del /q "%MAIN%.aux" "%MAIN%.log" "%MAIN%.nav" "%MAIN%.out" "%MAIN%.snm" "%MAIN%.toc" "%MAIN%.vrb" "%MAIN%.xdv" "%MAIN%.synctex.gz" 2>nul

xelatex "%MAIN%.tex"
xelatex "%MAIN%.tex"

popd
endlocal