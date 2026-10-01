@echo off
rem PromptInjectionFinder - auf die neueste Release-Version aktualisieren (Windows)
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Noch nicht eingerichtet. Bitte zuerst run_windows.bat starten.
  goto end
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m pif update %*
:end
pause
