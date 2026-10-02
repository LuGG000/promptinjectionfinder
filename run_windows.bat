@echo off
rem PromptInjectionFinder - starts the offline web interface (Windows).
rem The first start creates a private virtual environment (.venv); if it stops working
rem (e.g. the Python it was made with was removed), it is recreated automatically.
rem With PIF_LAUNCH=cli (set by bin\pif.cmd from install.ps1) it runs "pif <args>" in the
rem current folder instead and does not pause.
setlocal
set "ROOT=%~dp0"
set "VENV=%~dp0.venv"
set "VPY=%~dp0.venv\Scripts\python.exe"
set "MODE=%PIF_LAUNCH%"
set "PIF_LAUNCH="

if not exist "%VENV%" goto create
"%VPY%" -c "import sys" >nul 2>nul && goto deps
echo The Python environment no longer works (Python updated or removed?) - recreating it ... 1>&2
rmdir /s /q "%VENV%"

:create
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul || goto nopython
echo Creating virtual environment (one time) ... 1>&2
%PY% -m venv "%VENV%" 1>&2 || goto venvfail

:deps
"%VPY%" -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('pymupdf') and u.find_spec('numpy') else 1)" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies ^(one time, needs internet^) ... 1>&2
  "%VPY%" -m pip install -r "%ROOT%requirements.txt" 1>&2 || goto pipfail
)
set PYTHONUTF8=1
set "PP=%ROOT%"
if defined PYTHONPATH set "PP=%ROOT%;%PYTHONPATH%"
set "PYTHONPATH=%PP%"
rem python and the jump on one line: "pif update" may replace this file while python runs
rem (a label is looked up again, so keep :cli_done in future versions)
if /i "%MODE%"=="cli" "%VPY%" -m pif %* & goto cli_done

cd /d "%ROOT%"
rem One time: start menu entry for this copy, so it can be found via Windows search
rem (skipped if one exists already, e.g. from install.ps1, or with PIF_NO_SHORTCUTS).
if defined PIF_NO_SHORTCUTS goto run
if exist ".venv\.pif-shortcut" goto run
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l = Join-Path ([Environment]::GetFolderPath('Programs')) 'PromptInjectionFinder.lnk'; if (-not (Test-Path $l)) { $s = (New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath = '%~dp0run_windows.bat'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Check documents and web pages for hidden prompt injections'; $s.IconLocation = $env:SystemRoot + '\System32\shell32.dll,22'; $s.Save(); Write-Host 'Start menu entry PromptInjectionFinder created.' }" && type nul > ".venv\.pif-shortcut"
:run
rem The server gets a window of its own without a batch file around it: Ctrl+C then simply closes
rem it (a batch file would ask "Terminate batch job (Y/N)?" in the Windows display language).
set PIF_OWN_WINDOW=1
start "PromptInjectionFinder" "%VPY%" -m pif gui %*
exit /b

:nopython
echo Python 3.9 or newer was not found. 1>&2
echo Please install it from https://www.python.org (tick "Add python.exe to PATH") 1>&2
echo or: winget install Python.Python.3.12 1>&2
goto end
:venvfail
echo Could not create the virtual environment. 1>&2
goto end
:pipfail
echo Installing the dependencies failed (internet connection?). 1>&2
:end
if /i "%MODE%"=="cli" exit /b 1
rem own text instead of plain "pause", whose prompt is in the Windows display language
echo Press any key to close this window . . .
pause >nul
exit /b 1
:cli_done
exit /b %errorlevel%
