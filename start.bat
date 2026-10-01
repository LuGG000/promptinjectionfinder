@echo off
rem PromptInjectionFinder - startet die Offline-Oberflaeche
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -c "import pymupdf, numpy" >nul 2>nul
if errorlevel 1 (
  echo Installiere Abhaengigkeiten ^(einmalig, benoetigt Internet^)...
  %PY% -m pip install -r requirements.txt || (echo Installation fehlgeschlagen & pause & exit /b 1)
)
set PYTHONUTF8=1
%PY% -m pif gui %*
pause
