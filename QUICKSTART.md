# Quickstart Guide

Get the HR Screening Tool running on a fresh Windows machine from scratch.

---

## Step 1 — Check prerequisites

Open **PowerShell** and run each check below.

### Python version

```powershell
py --list
```

You need **Python 3.12** in the list. If you only see 3.13 or 3.14 (or nothing), go to Step 2.  
If 3.12 is already listed, skip to Step 3.

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

## Step 2 — Install Python 3.12

> Skip this step if `py --list` already shows `-V:3.12`.

```powershell
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
```

Close and re-open PowerShell after installation, then confirm:

```powershell
py --list
```

You should now see `-V:3.12` in the list.

---

## Step 3 — Install Visual C++ 2022 Redistributable

PyTorch (required by docling) needs the **2022** runtime. The 2019 version that ships with many machines is not sufficient.

```powershell
winget install Microsoft.VCRedist.2015+.x64 --accept-package-agreements --accept-source-agreements
```

> This is safe to run even if already installed — winget will report "already installed" and exit cleanly.

---

## Step 4 — Clone the repository

```powershell
git clone <repo-url>
cd HR-Screening---v2-claude-windows
```

---

## Step 5 — Create the Python 3.12 virtual environment

```powershell
py -3.12 -m venv .venv
```

Verify it was created with the correct Python version:

```powershell
.\.venv\Scripts\python.exe --version
```

Expected output: `Python 3.12.x`

---

## Step 6 — Install dependencies

```powershell
.\.venv\Scripts\pip install docling colorama
```

This will take **3–5 minutes** — docling pulls in PyTorch, Transformers, and several ML libraries.  
You will see a long list of packages being downloaded. This is normal.

### Optional: GPU support

Skip this if you don't have a dedicated GPU (CPU mode works fine for most workloads).

**NVIDIA GPU (CUDA):**
```powershell
.\.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cu121
```

**AMD / Intel GPU (DirectML):**
```powershell
.\.venv\Scripts\pip install torch-directml
```

---

## Step 7 — Verify the installation

Run these checks one at a time. Each should print `OK` with no errors.

### Check docling (PDF support)
```powershell
.\.venv\Scripts\python.exe -c "from docling.document_converter import DocumentConverter; print('docling OK')"
```

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
   PDF extraction: Docling (IBM) -- High-accuracy Markdown
==============================================================

  Main Menu
  [1] Screen New Resumes ...
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `docling not installed` warning on startup | Running with system Python instead of venv | Use `.\run.ps1`, not `python hr_screening_tool_v2_win.py` |
| `OSError: [WinError 1114] c10.dll` | Missing Visual C++ 2022 runtime | Re-run Step 3 |
| `Claude Code is not installed or not in PATH` | Claude desktop app not installed | Install from https://claude.ai/code |
| `py --list` does not show 3.12 after install | PowerShell session is stale | Close and re-open PowerShell |
| pip install hangs for a long time | Large ML model downloads | Wait — PyTorch alone is ~2 GB |
| `GPU: None (CPU mode)` on startup | No CUDA/DirectML torch installed | Normal if no GPU — tool works fine on CPU |
