@echo off
rem PromptInjectionFinder - update to the newest release (Windows)
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Not set up yet. Please start run_windows.bat first.
  goto end
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m pif update %*
:end
pause
