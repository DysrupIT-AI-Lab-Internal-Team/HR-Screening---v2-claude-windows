# HR Screening Tool v2 - automated setup + launch
#
# One-command bootstrap that mirrors QUICKSTART.md:
#   1. Check prerequisites (uv, Claude Code)
#   2. Sync dependencies from pyproject.toml / uv.lock  (creates the .venv)
#   3. Create the local .env from .env.example
#   4. Create the resumes\ jd\ results\ input folders
#   5. (optional) Pre-download docling OCR / layout models
#   6. Launch the tool
#
# Usage:
#   .\setup.ps1                 # set up, then run the Docling tool
#   .\setup.ps1 -Deepseek       # set up, then run the Deepseek OCR variant
#   .\setup.ps1 -DownloadModels # also pre-fetch docling models (needs internet)
#   .\setup.ps1 -SetupOnly      # set up only, do not launch the tool

[CmdletBinding()]
param(
    [switch]$Deepseek,
    [switch]$DownloadModels,
    [switch]$SetupOnly
)

$ErrorActionPreference = "Stop"

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
Set-Location $scriptDir

function Write-Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)       { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)     { Write-Host "    [!]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)      { Write-Host "    [X]  $msg" -ForegroundColor Red }

# --- 1. Prerequisites ---
Write-Step 1 "Checking prerequisites"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warn "uv not found. Attempting to install via winget..."
    try {
        winget install astral-sh.uv --accept-package-agreements --accept-source-agreements
    } catch {
        Write-Err "Could not install uv automatically."
        Write-Err "Install it manually, then re-open PowerShell and re-run:"
        Write-Err "    winget install astral-sh.uv"
        exit 1
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Err "uv installed but not on PATH yet. Close and re-open PowerShell, then re-run."
        exit 1
    }
}
Write-Ok "uv: $((uv --version))"

$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($claude) {
    Write-Ok "Claude Code: $($claude.Source)"
} else {
    # The desktop app installs claude.exe in a versioned subfolder not on PATH.
    $found = $false
    $packages = Join-Path $env:LOCALAPPDATA "Packages"
    if (Test-Path $packages) {
        foreach ($pkg in Get-ChildItem $packages -Directory) {
            if ($pkg.Name -like "*claude*") { $found = $true; break }
        }
    }
    if ($found) {
        Write-Ok "Claude Code desktop app detected (the tool locates claude.exe automatically)."
    } else {
        Write-Warn "Claude Code not detected. Install it from https://claude.ai/code before running screenings."
    }
}

# --- 2. Dependencies ---
Write-Step 2 "Installing dependencies (uv sync)"
uv sync
Write-Ok "Dependencies synced into .venv"

# --- 3. Configuration (.env) ---
Write-Step 3 "Setting up .env"
$envFile = Join-Path $scriptDir ".env"
$envExample = Join-Path $scriptDir ".env.example"
if (Test-Path $envFile) {
    Write-Ok ".env already exists - leaving it untouched."
} elseif (Test-Path $envExample) {
    Copy-Item $envExample $envFile
    Write-Ok "Created .env from .env.example (CLAUDE_MODEL is blank = Claude Code default)."
} else {
    Write-Warn ".env.example not found - skipping .env creation."
}

# --- 4. Input folders ---
Write-Step 4 "Creating input folders"
foreach ($dir in @("resumes", "jd", "results")) {
    $path = Join-Path $scriptDir $dir
    if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
}
Write-Ok "resumes\, jd\, results\ ready."

# --- 5. Pre-download docling models (optional) ---
if ($DownloadModels) {
    Write-Step 5 "Pre-downloading docling OCR / layout models"
    $doclingTools = Join-Path $scriptDir ".venv\Scripts\docling-tools.exe"
    if (Test-Path $doclingTools) {
        & $doclingTools models download
        Write-Ok "Models cached."
    } else {
        Write-Warn "docling-tools.exe not found - skipping model pre-download."
    }
}

# --- 6. Launch ---
if ($SetupOnly) {
    Write-Host "`nSetup complete. Run the tool with:  .\run.ps1" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $venvPython)) {
    Write-Err "Virtual environment Python not found at $venvPython. Setup may have failed."
    exit 1
}

if ($Deepseek) {
    Write-Step 6 "Launching HR Screening Tool (Deepseek OCR variant)"
    & $venvPython (Join-Path $scriptDir "hr_screening_tool_v2_deepseek_ocr.py")
} else {
    Write-Step 6 "Launching HR Screening Tool (Docling)"
    & $venvPython (Join-Path $scriptDir "hr_screening_tool_v2_win.py")
}
