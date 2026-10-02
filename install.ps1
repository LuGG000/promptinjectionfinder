# PromptInjectionFinder - install / update for Windows.
#
#   irm https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.ps1 | iex
#   or inside a downloaded copy:  powershell -ExecutionPolicy Bypass -File install.ps1
#
# Installs to %LOCALAPPDATA%\PromptInjectionFinder (change with PIF_DIR), creates a private
# Python environment, shortcuts on the desktop and in the start menu (skip: PIF_NO_SHORTCUTS)
# and the command "pif" via <dir>\bin on the user PATH (skip: PIF_NO_PATH).
# Running it again updates to the newest release. The chosen options are kept in
# <dir>\.pif-install; "pif update" runs this script with PIF_LAUNCHERS_ONLY=1 to refresh the
# pif command after an update.
$ErrorActionPreference = 'Stop'
$Repo = if ($env:PIF_REPO) { $env:PIF_REPO } else { 'https://gitlab.com/LuGG000/promptinjectionfinder.git' }
$Dir = if ($env:PIF_DIR) { $env:PIF_DIR } else { Join-Path $env:LOCALAPPDATA 'PromptInjectionFinder' }
$Bin = Join-Path $Dir 'bin'
$Marker = Join-Path $Dir '.pif-install'
$venvPy = Join-Path $Dir '.venv\Scripts\python.exe'

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# options of an earlier installation, unless set explicitly now
if (Test-Path $Marker) {
    foreach ($line in Get-Content $Marker) {
        if ($line -match '^(PIF_NO_SHORTCUTS|PIF_NO_PATH)=(.*)$' -and -not [Environment]::GetEnvironmentVariable($Matches[1])) {
            Set-Item "env:$($Matches[1])" $Matches[2]
        }
    }
}

function Install-PifCommand {
    # bin\pif.cmd runs run_windows.bat in command line mode, which also repairs .venv when needed
    New-Item -ItemType Directory -Force $Bin | Out-Null
    $runBat = Join-Path $Dir 'run_windows.bat'
    if ((Test-Path $runBat) -and (Select-String -Quiet -SimpleMatch 'PIF_LAUNCH' $runBat)) {
        $body = @('set PIF_LAUNCH=cli', 'call "%~dp0..\run_windows.bat" %* & goto done')
    } else {  # program version without command line mode in run_windows.bat (before 1.3)
        $body = @('set "PYTHONPATH=%~dp0..;%PYTHONPATH%"', 'set PYTHONUTF8=1',
                  '"%~dp0..\.venv\Scripts\python.exe" -m pif %* & goto done')
    }
    Set-Content -Encoding ascii (Join-Path $Bin 'pif.cmd') (@('@echo off', 'setlocal') + $body + @(':done', 'exit /b %errorlevel%'))
    if ($env:PIF_NO_PATH) { return }
    # user PATH (HKCU, no admin rights), read unexpanded so %VAR% entries survive the rewrite
    $envKey = Get-Item 'HKCU:\Environment'
    $userPath = $envKey.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
    if (($userPath -split ';') -notcontains $Bin) {
        Say "Adding $Bin to the user PATH"
        $kind = if ($envKey.GetValueNames() -contains 'Path') { $envKey.GetValueKind('Path') } else { 'ExpandString' }
        $newPath = if ($userPath) { $userPath.TrimEnd(';') + ';' + $Bin } else { $Bin }
        Set-ItemProperty 'HKCU:\Environment' -Name Path -Type $kind -Value $newPath
        # tell Explorer so newly opened terminals see the new PATH
        Add-Type -Namespace PifWin -Name Native -MemberDefinition @'
[DllImport("user32.dll", CharSet = CharSet.Auto)]
public static extern System.IntPtr SendMessageTimeout(System.IntPtr hWnd, uint Msg, System.UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out System.UIntPtr lpdwResult);
'@
        $res = [UIntPtr]::Zero
        [PifWin.Native]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$res) | Out-Null
    }
    if (($env:Path -split ';') -notcontains $Bin) { $env:Path = "$env:Path;$Bin" }
}

if ($env:PIF_LAUNCHERS_ONLY) {
    Install-PifCommand
    return
}

function Find-Python {
    foreach ($cand in @(@('py', '-3'), @('python'), @('python3'))) {
        $exe = $cand[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $args_ = @()
        if ($cand.Count -gt 1) { $args_ = $cand[1..($cand.Count - 1)] }
        try {
            & $exe @args_ -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return , $cand }
        } catch { }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say 'Python is missing - installing Python 3.12 with winget'
        winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $py = Find-Python
    }
    if (-not $py) { throw 'Python 3.9+ is missing. Please install it from https://www.python.org (tick "Add python.exe to PATH") and run again.' }
}
$pyExe = $py[0]
$pyArgs = @()
if ($py.Count -gt 1) { $pyArgs = $py[1..($py.Count - 1)] }

function Install-Venv {
    # a .venv whose base Python was removed or replaced no longer starts: build it again
    if (Test-Path $venvPy) {
        $works = $false
        try { & $venvPy -c 'import sys' 2>$null | Out-Null; $works = $LASTEXITCODE -eq 0 } catch { }
        if (-not $works) {
            Say 'The Python environment no longer works (Python updated or removed?) - recreating it'
            Remove-Item -Recurse -Force (Join-Path $Dir '.venv')
        }
    }
    if (-not (Test-Path $venvPy)) {
        Say 'Creating Python environment'
        & $pyExe @pyArgs -m venv (Join-Path $Dir '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
    }
    Say 'Installing dependencies'
    & $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Dir 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed (internet connection?).' }
}

# ------------------------------------------------------------------ program files
if (Test-Path (Join-Path $Dir 'pif')) {
    Say "Existing installation found: $Dir - updating"
    Install-Venv
    Push-Location $Dir
    try { & $venvPy -m pif update } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Say 'Update not possible - the installed version is kept.' }
} elseif ($env:PIF_SOURCE) {
    Say "Copying program from $($env:PIF_SOURCE)"
    New-Item -ItemType Directory -Force $Dir | Out-Null
    robocopy $env:PIF_SOURCE $Dir /E /XD .venv .git dist build bin __pycache__ /XF .pif-install .pif-launchers /NFL /NDL /NJH /NJS /NP | Out-Null
} else {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'git is missing (needed for download and updates): winget install -e --id Git.Git  - then run again.'
    }
    $tags = git ls-remote --tags $Repo 2>$null | ForEach-Object { if ($_ -match 'refs/tags/(v\d+\.\d+(\.\d+)?)$') { $Matches[1] } }
    $tag = $tags | Sort-Object { [version]($_.TrimStart('v')) } | Select-Object -Last 1
    Say "Downloading PromptInjectionFinder $tag"
    New-Item -ItemType Directory -Force (Split-Path $Dir) | Out-Null
    git clone --quiet $Repo $Dir
    if ($LASTEXITCODE -ne 0) { throw 'Download failed (access to the GitLab project?).' }
    if ($tag) { git -C $Dir -c advice.detachedHead=false checkout --quiet $tag }
}

# ------------------------------------------------------------------ python environment
Install-Venv

# ------------------------------------------------------------------ shortcuts
if (-not $env:PIF_NO_SHORTCUTS) {
$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'PromptInjectionFinder.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'PromptInjectionFinder.lnk')
)
foreach ($lnkPath in $targets) {
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = Join-Path $Dir 'run_windows.bat'
    $lnk.WorkingDirectory = $Dir
    $lnk.Description = 'Check documents and web pages for hidden prompt injections'
    $lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,22"
    $lnk.Save()
}
$upd = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) 'Update PromptInjectionFinder.lnk'))
$upd.TargetPath = Join-Path $Dir 'update_windows.bat'
$upd.WorkingDirectory = $Dir
$upd.Save()
}

# ------------------------------------------------------------------ pif command
Install-PifCommand
Set-Content -Encoding ascii $Marker @("PIF_NO_SHORTCUTS=$($env:PIF_NO_SHORTCUTS)", "PIF_NO_PATH=$($env:PIF_NO_PATH)")

$version = & $venvPy -c "import sys; sys.path.insert(0, r'$Dir'); import pif; print(pif.__version__)"
Set-Content -Encoding ascii (Join-Path $Dir '.pif-launchers') $version
Say "Done: PromptInjectionFinder $version in $Dir"
if (-not $env:PIF_NO_SHORTCUTS) { Write-Host '    Start:         start menu / desktop "PromptInjectionFinder" (opens the browser)' }
Write-Host '    Command line:  pif scan <file>  |  pif scan-url <link>   (add --lang de for German; open a new terminal first)'
Write-Host '    Update:        pif update  or  start menu "Update PromptInjectionFinder"'
if ($env:PIF_NO_PATH) { Write-Host "    Note: $Bin is not on PATH (PIF_NO_PATH)." }
