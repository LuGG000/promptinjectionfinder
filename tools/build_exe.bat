@echo off
rem Builds dist\PromptInjectionFinder.exe (runs without a Python installation)
cd /d "%~dp0\.."
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install -r requirements.txt pyinstaller || exit /b 1
%PY% -m PyInstaller --noconfirm --onefile --name PromptInjectionFinder ^
  --add-data "pif\web;pif\web" --collect-all pymupdf --paths . tools\pif_app.py
echo.
echo Done: dist\PromptInjectionFinder.exe
