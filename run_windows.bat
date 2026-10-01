@echo off
rem PromptInjectionFinder - starts the offline web interface (Windows).
rem The first start creates a private virtual environment (.venv).
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto deps

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul || goto nopython

echo Creating virtual environment (one time) ...
%PY% -m venv .venv || goto venvfail

:deps
".venv\Scripts\python.exe" -c "import pymupdf, numpy" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies ^(one time, needs internet^) ...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto pipfail
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m pif gui %*
goto end

:nopython
echo Python 3.9 or newer was not found.
echo Please install it from https://www.python.org (tick "Add python.exe to PATH")
echo or: winget install Python.Python.3.12
goto end
:venvfail
echo Could not create the virtual environment.
goto end
:pipfail
echo Installing the dependencies failed (internet connection?).
:end
pause
