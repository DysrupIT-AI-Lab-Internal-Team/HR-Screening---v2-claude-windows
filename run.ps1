# HR Screening Tool v2 — launch via uv (Python 3.12)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[X] uv not found. Install it first:"
    Write-Host "    winget install astral-sh.uv"
    exit 1
}

# uv run syncs the environment from uv.lock (creating .venv if needed) and
# executes the tool inside it — no manual venv activation or pip required.
& uv run --project $scriptDir (Join-Path $scriptDir "hr_screening_tool_v2_win.py") @args
