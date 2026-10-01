@echo off
rem PromptInjectionFinder - startet die Offline-Weboberflaeche (Windows).
rem Beim ersten Start wird eine eigene virtuelle Umgebung (.venv) angelegt.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto deps

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul || goto nopython

echo Lege virtuelle Umgebung an (einmalig) ...
%PY% -m venv .venv || goto venvfail

:deps
".venv\Scripts\python.exe" -c "import pymupdf, numpy" >nul 2>nul
if errorlevel 1 (
  echo Installiere Abhaengigkeiten ^(einmalig, benoetigt Internet^) ...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto pipfail
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m pif gui %*
goto end

:nopython
echo Python 3.9 oder neuer wurde nicht gefunden.
echo Bitte von https://www.python.org installieren (Haken bei "Add python.exe to PATH" setzen)
echo oder: winget install Python.Python.3.12
goto end
:venvfail
echo Konnte keine virtuelle Umgebung anlegen.
goto end
:pipfail
echo Installation der Abhaengigkeiten fehlgeschlagen (Internetverbindung?).
:end
pause
