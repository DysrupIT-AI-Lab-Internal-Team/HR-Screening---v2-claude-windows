# Quickstart Guide

Get the HR Screening Tool running on a fresh Windows machine from scratch.

---

## Step 1 — Check prerequisites

Open **Windows PowerShell** Ensure that you are in 
```powershell
PS C:\Users\<your PC name>\Documents>
```

and run each check below.

### uv (Python package manager)

```powershell
uv --version
```

Should print a version (e.g. `uv 0.11.x`). If you get "not recognized", install it:

```powershell
winget install astral-sh.uv --accept-package-agreements --accept-source-agreements
```

Close and re-open PowerShell after installing.

### Claude Code

```powershell
where.exe claude
```

If you see a path — Claude is installed. If you get "Could not find files", install it first:  
Download and install the Claude desktop app from **https://claude.ai/code**, then re-open PowerShell.

### winget (package manager)

```powershell
winget --version
```

Should print a version number (e.g. `v1.28.x`). winget ships with Windows 11 by default.  
If missing, update the **App Installer** package from the Microsoft Store.

---

## Step 2 — Install Visual C++ 2022 Redistributable

PyTorch (required by docling) needs the **2022** runtime. The 2019 version that ships with many machines is not sufficient.

```powershell
winget install Microsoft.VCRedist.2015+.x64 --accept-package-agreements --accept-source-agreements
```

> This is safe to run even if already installed — winget will report "already installed" and exit cleanly.

---

## Step 3 — Clone the repository

```powershell
git clone https://github.com/DysrupIT-AI-Lab-Internal-Team/HR-Screening---v2-claude-windows.git
cd HR-Screening---v2-claude-windows
```

---

## Step 4 — Create the Python 3.12 virtual environment

```powershell
uv venv --python 3.12 .venv
```
then activate it using 
```
.venv\Scripts\activate
```

If Python 3.12 isn't installed on the machine, uv downloads a standalone build
automatically — no winget/python.org install needed.

Verify it was created with the correct Python version:

```powershell
.\.venv\Scripts\python.exe --version
```

Expected output: `Python 3.12.x`

---

## Step 5 — Install dependencies

```powershell
uv pip install "docling[full]" colorama
```

uv installs into the `.venv` in the current folder automatically (no need to activate it).

> **Use `docling[full]`, not plain `docling`.** The plain package is a *slim* build
> that does **not** include PyTorch. Without torch, docling's OCR / layout pipeline
> cannot even import, and PDF processing will fail (there is no pypdf fallback).
> The `[full]` extra pulls in `torch` + `torchvision`, which is what the tool's
> Windows DLL workaround loads at startup.

The **first** time you do this, uv downloads PyTorch (~120 MB wheel), Transformers, and
several ML libraries into its global cache. On any later venv — this project or another —
uv hardlinks the same cached wheels instead of re-downloading or re-copying them, so it's
near-instant and uses no extra disk space.

### Optional: GPU support

Skip this if you don't have a dedicated GPU (CPU mode works fine for most workloads).

**NVIDIA GPU (CUDA):**
```powershell
uv pip install torch --index-url https://download.pytorch.org/whl/cu121
```

**AMD / Intel GPU (DirectML):**
```powershell
uv pip install torch-directml
```

---

## Step 6 — Verify the installation

Run these checks one at a time. Each should print `OK` with no errors.

### Check docling + torch (PDF support)
```powershell
.\.venv\Scripts\python.exe -c "import torch; from docling.document_converter import DocumentConverter; print('docling + torch OK -', torch.__version__)"
```

If this raises `ModuleNotFoundError: No module named 'torch'`, you installed the slim
package. Re-run Step 5 with `docling[full]`.

### Check Claude CLI is detected
```powershell
.\.venv\Scripts\python.exe -c "
import shutil, os
from pathlib import Path
hit = shutil.which('claude')
if not hit:
    base = Path(os.environ.get('LOCALAPPDATA','')) / 'Packages'
    for pkg in base.iterdir():
        if 'claude' in pkg.name.lower():
            for sub in sorted((pkg / 'LocalCache' / 'Roaming' / 'Claude' / 'claude-code').iterdir(), reverse=True):
                exe = sub / 'claude.exe'
                if exe.is_file():
                    hit = str(exe)
                    break
print('Claude CLI:', hit or 'NOT FOUND')
"
```

Expected output: `Claude CLI: C:\Users\...\claude.exe`  
If it prints `NOT FOUND`, re-install the Claude desktop app and re-run.

### Check GPU detection (optional)
```powershell
.\.venv\Scripts\python.exe -c "
try:
    import torch
    print('torch OK — CUDA:', torch.cuda.is_available())
except Exception as e:
    print('torch not available (CPU mode will be used):', e)
"
```

---

## Step 7 — Pre-download the OCR / layout models (recommended)

On the **first** PDF it processes, docling downloads its ML model weights from the
internet — the RapidOCR detection/classification/recognition models (~40 MB from
modelscope.cn) plus docling's layout and table-structure models (from Hugging Face).
This happens automatically, but it means the *first* resume is slow and **requires an
internet connection**.

To get this out of the way now (and confirm processing will work), pre-fetch the
models with docling's downloader:

```powershell
.\.venv\Scripts\docling-tools.exe models download
```

> The models are cached under your user profile, so this only needs to run once per
> machine. If the machine that runs screenings has no internet access, run this step
> on it while it is still online — processing itself works offline once models are cached.

---

## Step 8 — Set up folders

Create the required input folders if they don't exist:

```powershell
New-Item -ItemType Directory -Force resumes, jd, results
```

- Drop **resume files** (`.pdf` or `.txt`) into subfolders under `resumes\`  
  e.g. `resumes\DevOps Engineer\john_doe.pdf`
- Drop **job description files** (`.txt` or `.md`) into `jd\`  
  e.g. `jd\devops_engineer.txt`

---

## Step 9 — Run the tool

```powershell
.\run.ps1
```

You should see the main menu:

```
==============================================================
   HR SCREENING TOOL v2  --  Windows Optimized
   Powered by Claude Code Pro
   PDF extraction: Docling -- OCR + layout-aware Markdown
==============================================================

  Main Menu
  [1] Screen New Resumes ...
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `docling not installed` / PDF support disabled | Slim docling installed without torch, **or** running system Python instead of venv | Re-run Step 5 with `docling[full]`; launch via `.\run.ps1`, not `python hr_screening_tool_v2_win.py` |
| `ModuleNotFoundError: No module named 'torch'` | Installed plain `docling` (slim) instead of `docling[full]` | `uv pip install "docling[full]"` |
| First resume hangs / `connection` errors during processing | OCR/layout models downloading on first run | Run Step 7 while online; needs internet on first use |
| `OSError: [WinError 1114] c10.dll` | Missing Visual C++ 2022 runtime | Re-run Step 2 |
| `Claude Code is not installed or not in PATH` | Claude desktop app not installed | Install from https://claude.ai/code |
| `uv` not recognized | uv not installed or PATH stale | `winget install astral-sh.uv`, then re-open PowerShell |
| `uv pip install` fails to find a venv | `.venv` not created yet, or not in project folder | Run Step 5 first; run uv commands from the project root |
| First install is slow / downloads a lot | Cold uv cache (first machine ever) | One-time — later venvs hardlink from the cache instantly |
| `GPU: None (CPU mode)` on startup | No CUDA/DirectML torch installed | Normal if no GPU — tool works fine on CPU |
