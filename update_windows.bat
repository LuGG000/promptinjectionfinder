@echo off
rem PromptInjectionFinder - update to the newest release (Windows)
rem run_windows.bat in command line mode also repairs .venv first when needed.
rem One line on purpose: the update may replace this file while it runs.
setlocal
set PIF_LAUNCH=cli
call "%~dp0run_windows.bat" update %* & echo Press any key to close this window . . . & pause >nul & exit /b
