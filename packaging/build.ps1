<#
.SYNOPSIS
    Build the Windows desktop distribution (and installer, if Inno Setup is
    available) from a clean checkout. Task 15.

.DESCRIPTION
    Creates a throwaway build venv (kept separate from any dev venv you use
    for day-to-day work), installs the app with its gui+windows extras,
    runs PyInstaller against packaging\build.spec, and -- if ISCC.exe (Inno
    Setup's compiler) is on PATH or installed at its default location --
    compiles packaging\installer.iss into a Setup.exe.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1

.EXAMPLE
    # Skip the offline test run (it's on by default as a build gate)
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipTests
#>
param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "== Repo root: $RepoRoot =="

Write-Host "== Creating build venv (.venv-build) =="
python -m venv .venv-build
& .\.venv-build\Scripts\Activate.ps1

Write-Host "== Installing manuscript-validator (gui + windows extras) =="
python -m pip install --upgrade pip
# A non-editable install: PyInstaller's static import analysis does not
# reliably follow the finder that `pip install -e` (PEP 660) registers.
pip install ".[gui,windows,dev]"

if (-not $SkipTests) {
    Write-Host "== Running the offline test suite as a build gate =="
    # Same default marker filter as CI: skips `live` (real Gemini calls) and
    # `windows` (this is where those actually run, but the DPAPI round trip
    # itself still needs a manual smoke test -- see the checklist).
    pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "Test suite failed -- fix before building a distributable."
    }
}

Write-Host "== Running PyInstaller =="
pyinstaller packaging\build.spec --noconfirm --clean

$exePath = Join-Path $RepoRoot "dist\ManuscriptValidator\ManuscriptValidator.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected build output not found: $exePath"
}
Write-Host "== Build output: $exePath =="

Write-Host "== Looking for Inno Setup's compiler (ISCC.exe) =="
$isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($isccCommand) {
    $isccPath = $isccCommand.Path
} else {
    $default = "${Env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $default) {
        $isccPath = $default
    }
}

if ($isccPath) {
    Write-Host "== Building installer with Inno Setup =="
    & $isccPath (Join-Path $RepoRoot "packaging\installer.iss")
    Write-Host "== Installer output: dist\installer\ =="
} else {
    Write-Host ""
    Write-Host "Inno Setup (ISCC.exe) not found -- skipped the installer step."
    Write-Host "Install it from https://jrsoftware.org/isdl.php, then re-run this"
    Write-Host "script (or just: ISCC packaging\installer.iss) to produce Setup.exe."
}
