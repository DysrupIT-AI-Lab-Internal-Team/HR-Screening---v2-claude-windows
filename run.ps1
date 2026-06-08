# HR Screening Tool v2 — launch with Python 3.12 venv
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[X] Virtual environment not found. Run setup first:"
    Write-Host "    uv venv --python 3.12 .venv"
    Write-Host "    uv pip install `"docling[full]`" colorama"
    exit 1
}

& $venvPython (Join-Path $scriptDir "hr_screening_tool_v2_win.py") @args
