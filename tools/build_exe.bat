@echo off
rem Baut dist\PromptInjectionFinder.exe (laeuft ohne Python-Installation)
cd /d "%~dp0\.."
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install -r requirements.txt pyinstaller || exit /b 1
%PY% -m PyInstaller --noconfirm --onefile --name PromptInjectionFinder ^
  --add-data "pif\web;pif\web" --collect-all pymupdf --paths . tools\pif_app.py
echo.
echo Fertig: dist\PromptInjectionFinder.exe
