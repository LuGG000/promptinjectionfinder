# PromptInjectionFinder - install / update for Windows.
#
#   irm https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.ps1 | iex
#   or inside a downloaded copy:  powershell -ExecutionPolicy Bypass -File install.ps1
#
# Installs to %LOCALAPPDATA%\PromptInjectionFinder (change with PIF_DIR), creates a private
# Python environment and shortcuts on the desktop and in the start menu.
# Running it again updates to the newest release.
$ErrorActionPreference = 'Stop'
$Repo = if ($env:PIF_REPO) { $env:PIF_REPO } else { 'https://gitlab.com/LuGG000/promptinjectionfinder.git' }
$Dir = if ($env:PIF_DIR) { $env:PIF_DIR } else { Join-Path $env:LOCALAPPDATA 'PromptInjectionFinder' }

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

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

# ------------------------------------------------------------------ program files
$venvPy = Join-Path $Dir '.venv\Scripts\python.exe'
if (Test-Path (Join-Path $Dir 'pif')) {
    Say "Existing installation found: $Dir - updating"
    if (Test-Path $venvPy) {
        & $venvPy -m pif update
        if ($LASTEXITCODE -ne 0) { Say 'Update not possible - the installed version is kept.' }
    }
} elseif ($env:PIF_SOURCE) {
    Say "Copying program from $($env:PIF_SOURCE)"
    New-Item -ItemType Directory -Force $Dir | Out-Null
    robocopy $env:PIF_SOURCE $Dir /E /XD .venv .git dist build __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
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
if (-not (Test-Path $venvPy)) {
    Say 'Creating Python environment'
    & $pyExe @pyArgs -m venv (Join-Path $Dir '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
Say 'Installing dependencies'
& $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Dir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip install failed (internet connection?).' }

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

$version = & $venvPy -c "import sys; sys.path.insert(0, r'$Dir'); import pif; print(pif.__version__)"
Say "Done: PromptInjectionFinder $version in $Dir"
Write-Host '    Start:   desktop shortcut "PromptInjectionFinder" (opens the browser)'
Write-Host '    Update:  start menu "Update PromptInjectionFinder"  or  update_windows.bat'
