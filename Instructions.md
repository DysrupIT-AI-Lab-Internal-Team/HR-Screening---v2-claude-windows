Here's how to run it on your Windows machine using Claude Code CLI only (no IDE needed):

Step-by-Step
1. Open PowerShell or Windows Terminal
Press Win + X → Terminal (or search "PowerShell").

2. Install Claude Code CLI (if not already)
powershell
npm install -g @anthropic-ai/claude-code
claude login
3. Install Python dependencies (with uv)
powershell
uv venv --python 3.12 .venv
uv pip install "docling[full]" colorama
Skip this if you only have .txt resumes. (uv installs uv with `winget install astral-sh.uv`; it caches and hardlinks the large wheels so they aren't duplicated per project.)

4. Set up your folder structure
Based on your current setup, your HR-Screening Windows folder should look like:

HR-Screening Windows/
├── hr_screening_tool_v2_win.py
├── resumes/
│   └── IBM_iSeries_Developer/      ← subfolder matching the role
│       ├── candidate_1.pdf
│       └── candidate_2.txt
├── jd/
│   └── IBM_iSeries_Developer.md    ← you already have this
└── results/                         ← auto-created on first run
5. Run it

cd "C:\Users\YourName\Documents\HR-Screening Windows"
python hr_screening_tool_v2_win.py
That's it — the interactive menu will appear and guide you through everything.

Quick Troubleshooting
Issue	Fix
claude not found	Run where claude — if missing, restart terminal after npm install -g
python not found	Try python3 or py instead
Garbled characters	Use Windows Terminal (the modern one), not legacy cmd.exe
Permission denied	Run PowerShell as Administrator
Verify everything works before running:
powershell
claude -p "Say hello" --output-format text
python --version
If both commands return output, you're good to go.

