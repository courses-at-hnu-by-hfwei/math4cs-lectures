@echo off
setlocal EnableExtensions EnableDelayedExpansion

pushd "%~dp0"

set "MAIN="
for %%F in (*.tex) do (
    findstr /b /c:"\documentclass" "%%F" >nul 2>&1
    if not errorlevel 1 (
        set "MAIN=%%~nF"
        goto :main_found
    )
)

echo No LaTeX main file found in "%CD%".
popd
exit /b 1

:main_found
set "HANDOUT_JOB=%MAIN%-handout"
set "HANDOUT_WRAPPER=%TEMP%\%MAIN%-handout-wrapper-%RANDOM%%RANDOM%.tex"

del /q "%MAIN%.aux" "%MAIN%.log" "%MAIN%.nav" "%MAIN%.out" "%MAIN%.snm" "%MAIN%.toc" "%MAIN%.vrb" "%MAIN%.xdv" "%MAIN%.synctex.gz" 2>nul
del /q "%HANDOUT_JOB%.aux" "%HANDOUT_JOB%.log" "%HANDOUT_JOB%.nav" "%HANDOUT_JOB%.out" "%HANDOUT_JOB%.snm" "%HANDOUT_JOB%.toc" "%HANDOUT_JOB%.vrb" "%HANDOUT_JOB%.xdv" "%HANDOUT_JOB%.synctex.gz" 2>nul

where xelatex >nul 2>&1
if errorlevel 1 (
    echo xelatex was not found in PATH.
    popd
    exit /b 1
)

> "%HANDOUT_WRAPPER%" echo \PassOptionsToClass{handout}{beamer}
>> "%HANDOUT_WRAPPER%" echo \input{%MAIN%.tex}

call :compile_handout
if errorlevel 1 goto :cleanup

call :compile_regular
if errorlevel 1 goto :cleanup

echo Build finished: "%HANDOUT_JOB%.pdf" and "%MAIN%.pdf"
call :git_sync
if errorlevel 1 goto :cleanup
set "EXITCODE=0"
goto :cleanup

:compile_handout
echo [1/2] xelatex handout pass 1: %HANDOUT_JOB%.pdf
xelatex -halt-on-error -interaction=nonstopmode -jobname="%HANDOUT_JOB%" "%HANDOUT_WRAPPER%"
if errorlevel 1 exit /b 1

echo [2/2] xelatex handout pass 2: %HANDOUT_JOB%.pdf
xelatex -halt-on-error -interaction=nonstopmode -jobname="%HANDOUT_JOB%" "%HANDOUT_WRAPPER%"
if errorlevel 1 exit /b 1

exit /b 0

:compile_regular
echo [1/2] xelatex regular pass 1: %MAIN%.pdf
xelatex -halt-on-error -interaction=nonstopmode "%MAIN%.tex"
if errorlevel 1 exit /b 1

echo [2/2] xelatex regular pass 2: %MAIN%.pdf
xelatex -halt-on-error -interaction=nonstopmode "%MAIN%.tex"
if errorlevel 1 exit /b 1

exit /b 0

:git_sync
where git >nul 2>&1
if errorlevel 1 (
    echo git was not found in PATH.
    exit /b 1
)

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo Current directory is not inside a Git repository.
    exit /b 1
)

git status --porcelain --untracked-files=normal -- . | findstr "." >nul
if errorlevel 1 (
    echo No Git changes detected in the current directory. Skipping git commit and git push.
    exit /b 0
)

setlocal DisableDelayedExpansion
set "COMMIT_MSG="
set /p "COMMIT_MSG=Commit message (leave empty to skip git commit/push): "
if not defined COMMIT_MSG (
    echo Skipping git commit and git push.
    endlocal & exit /b 0
)

git add -A .
if errorlevel 1 (
    endlocal & exit /b 1
)

git diff --cached --quiet --exit-code -- .
if not errorlevel 1 (
    echo No changes staged in the current directory. Skipping git commit and git push.
    endlocal & exit /b 0
)

git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    endlocal & exit /b 1
)

git push
set "GIT_EXIT=%ERRORLEVEL%"
if not "%GIT_EXIT%"=="0" (
    endlocal & exit /b %GIT_EXIT%
)

echo Git sync finished.
endlocal & exit /b 0

:cleanup
if exist "%HANDOUT_WRAPPER%" del /q "%HANDOUT_WRAPPER%"
del /q "%HANDOUT_JOB%.aux" "%HANDOUT_JOB%.log" "%HANDOUT_JOB%.nav" "%HANDOUT_JOB%.out" "%HANDOUT_JOB%.snm" "%HANDOUT_JOB%.toc" "%HANDOUT_JOB%.vrb" "%HANDOUT_JOB%.xdv" "%HANDOUT_JOB%.synctex.gz" 2>nul
if not defined EXITCODE set "EXITCODE=1"
popd
endlocal & exit /b %EXITCODE%