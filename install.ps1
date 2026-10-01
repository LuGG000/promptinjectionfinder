# PromptInjectionFinder - Installation / Update fuer Windows.
#
#   irm https://gitlab.com/LuGG000/promptinjectionfinder/-/raw/main/install.ps1 | iex
#   oder im heruntergeladenen Ordner:  powershell -ExecutionPolicy Bypass -File install.ps1
#
# Installiert nach %LOCALAPPDATA%\PromptInjectionFinder (PIF_DIR aendert das), legt eine eigene
# Python-Umgebung sowie Verknuepfungen auf dem Desktop und im Startmenue an.
# Ein erneuter Aufruf aktualisiert auf das neueste Release.
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
        Say 'Python fehlt - installiere Python 3.12 mit winget'
        winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $py = Find-Python
    }
    if (-not $py) { throw 'Python 3.9+ fehlt. Bitte von https://www.python.org installieren (Haken "Add python.exe to PATH") und erneut starten.' }
}
$pyExe = $py[0]
$pyArgs = @()
if ($py.Count -gt 1) { $pyArgs = $py[1..($py.Count - 1)] }

# ------------------------------------------------------------------ program files
$venvPy = Join-Path $Dir '.venv\Scripts\python.exe'
if (Test-Path (Join-Path $Dir 'pif')) {
    Say "Bestehende Installation gefunden: $Dir - aktualisiere"
    if (Test-Path $venvPy) {
        & $venvPy -m pif update
        if ($LASTEXITCODE -ne 0) { Say 'Update nicht moeglich - vorhandene Version bleibt installiert.' }
    }
} elseif ($env:PIF_SOURCE) {
    Say "Kopiere Programm aus $($env:PIF_SOURCE)"
    New-Item -ItemType Directory -Force $Dir | Out-Null
    robocopy $env:PIF_SOURCE $Dir /E /XD .venv .git dist build __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
} else {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'git fehlt (fuer Download und Updates): winget install -e --id Git.Git  - danach erneut starten.'
    }
    $tags = git ls-remote --tags $Repo 2>$null | ForEach-Object { if ($_ -match 'refs/tags/(v\d+\.\d+(\.\d+)?)$') { $Matches[1] } }
    $tag = $tags | Sort-Object { [version]($_.TrimStart('v')) } | Select-Object -Last 1
    Say "Lade PromptInjectionFinder $tag herunter"
    New-Item -ItemType Directory -Force (Split-Path $Dir) | Out-Null
    if ($tag) { git -c advice.detachedHead=false clone --quiet --depth 50 --branch $tag $Repo $Dir }
    else { git clone --quiet $Repo $Dir }
    if ($LASTEXITCODE -ne 0) { throw 'Download fehlgeschlagen (Zugriff auf das GitLab-Projekt?).' }
}

# ------------------------------------------------------------------ python environment
if (-not (Test-Path $venvPy)) {
    Say 'Lege Python-Umgebung an'
    & $pyExe @pyArgs -m venv (Join-Path $Dir '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Konnte keine virtuelle Umgebung anlegen.' }
}
Say 'Installiere Abhaengigkeiten'
& $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Dir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip install fehlgeschlagen (Internetverbindung?).' }

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
    $lnk.Description = 'Dokumente und Webseiten auf versteckte Prompt Injections pruefen'
    $lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,22"
    $lnk.Save()
}
$upd = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) 'PromptInjectionFinder aktualisieren.lnk'))
$upd.TargetPath = Join-Path $Dir 'update_windows.bat'
$upd.WorkingDirectory = $Dir
$upd.Save()
}

$version = & $venvPy -c "import sys; sys.path.insert(0, r'$Dir'); import pif; print(pif.__version__)"
Say "Fertig: PromptInjectionFinder $version in $Dir"
Write-Host '    Starten:       Desktop-Verknuepfung "PromptInjectionFinder" (oeffnet den Browser)'
Write-Host '    Aktualisieren: Startmenue "PromptInjectionFinder aktualisieren"  oder  update_windows.bat'
