# DysrupIT AI Team — Development Standards

**Owner:** Julius Suarez  
**Applies to:** All AI Team projects and apps  
**Last updated:** 2026-06-08

---

## 1. Purpose

These standards exist to keep our apps **secure, simple, and maintainable** as the team grows.
Junior devs inheriting existing code and building new apps must follow these standards.
Any deviation requires an approved PR — see [Section 7: Proposing New Tech](#7-proposing-new-tech).

---

## 2. Approved Tech Stack

Only the following tools are pre-approved. Everything else requires a proposal (Section 7).

### Python Runtime & Package Management

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Python version management + virtual envs + package management | Replaces pip, pyenv, venv |

- Reference guides:
  - Windows + OneDrive: https://dev.to/williamandresr/uv-on-windows-with-onedrive-centralized-virtual-environments-331b
  - macOS: https://mac.install.guide/python/install-uv
- Always use `uv init` to start a new project
- Always use `uv add <package>` — never `pip install` directly
- Commit both `pyproject.toml` and `uv.lock` to the repo

### AI / LLM

| Tool | Type | Usage |
|------|------|-------|
| **Claude Code CLI** | Cloud model | Primary AI backend — no API key required |
| **Ollama (local models)** | Local model | Offline/privacy-sensitive workloads only |

**Rules for Ollama / local models:**
- A local model is only approved for a given task if its output quality is **demonstrably at par** with Claude on that specific task.
- Before using a local model in production, run it against the same inputs as Claude and document the comparison.
- The model name and version used must be recorded in the project `README.md`.

### Version Control

- All projects are saved to **DysrupIT GitHub**.
- No personal or external repos.

### Configuration & Secrets

- Use **`.env` files** for all environment-specific config and secrets (see Section 4).
- Use **`.gitignore`** following the standards in Section 5.

### Architecture

- **No client-server architecture** (e.g., REST APIs, web servers, databases) without discussion and approval.
- Keep apps as **CLI tools or scripts** unless a different pattern is explicitly approved.
- No message queues, orchestration frameworks, or distributed systems without approval.

---

## 3. Python Coding Standards

### Project Structure

Every project must follow this layout:

```
project-name/
├── .env                  # Local secrets — never committed
├── .env.example          # Template with placeholder values — always committed
├── .gitignore
├── pyproject.toml        # uv project config
├── uv.lock               # uv lockfile
├── README.md
├── main.py               # Entry point (or descriptively named equivalent)
├── docs/                 # User-facing docs (optional)
└── memory/               # Claude Code session notes (if applicable)
```

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Variables | `snake_case` | `candidate_name` |
| Functions | `snake_case` | `load_resume()` |
| Classes | `PascalCase` | `ResumeParser` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_WORKERS = 4` |
| Files/modules | `snake_case` | `resume_parser.py` |

### Code Style Rules

- **Line length:** Max 88 characters (Black formatter standard).
- **Functions:** Keep them small — one function, one responsibility. If a function is longer than ~40 lines, consider splitting it.
- **No magic numbers:** Use named constants. `MAX_RETRIES = 3` not `for i in range(3)`.
- **No commented-out code:** Delete it. Git history preserves old versions.
- **Comments:** Only add a comment when the **why** is non-obvious. Do not explain what the code does — good names do that.
- **Imports:** Standard library first, third-party second, local last. One blank line between groups.

### Example: What Good Looks Like

```python
# Good
MAX_RESUMES_PER_BATCH = 10

def screen_resume(file_path: str, model: str) -> dict:
    text = extract_text(file_path)
    return analyze_with_llm(text, model)


# Bad
def process(f, m):  # processes the file
    t = get_text(f)
    # t = clean_text(t)  # old version
    result = llm(t, m, 3)  # 3 retries
    return result
```

---

## 4. .env — Security Rules

### What Goes in `.env`

- API keys, tokens, passwords
- URLs or hostnames that differ between environments (local vs prod)
- Model names or configuration that should be changeable without code edits
- Any value that would be a security risk if seen in a public repo

### What Never Goes in `.env`

- Hardcoded logic or business rules (those belong in code)
- Large data payloads

### Required Files

**`.env` (never committed):**
```
CLAUDE_MODEL=claude-sonnet-4-6
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma4:latest
```

**`.env.example` (always committed — placeholder values only):**
```
CLAUDE_MODEL=your-model-name-here
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=your-ollama-model-here
```

### Rules

1. `.env` must always be in `.gitignore` — no exceptions.
2. `.env.example` must always exist and stay up to date.
3. When you add a new variable to `.env`, add the key (with a placeholder value) to `.env.example` in the same commit.
4. Never hardcode secrets or credentials directly in code.
5. Load `.env` using `python-dotenv` (`uv add python-dotenv`).

```python
from dotenv import load_dotenv
import os

load_dotenv()
model = os.getenv("CLAUDE_MODEL")
```

---

## 5. .gitignore — Standards

Every project must include a `.gitignore` covering at minimum:

```gitignore
# Secrets
.env
*.env
.env.*
!.env.example

# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python

# uv / virtual environments
.venv/
venv/
env/

# Distribution / build
dist/
build/
*.egg-info/

# Testing
.pytest_cache/
.coverage
htmlcov/

# OS
.DS_Store
Thumbs.db
desktop.ini

# IDE
.vscode/
.idea/
*.swp
*.swo

# Project-specific outputs (adjust as needed)
outputs/
*.log
```

Do not strip or shrink this list. Add project-specific entries below the comment `# Project-specific outputs`.

---

## 6. Git & GitHub Workflow

### Commit Messages

Write commit messages that explain **why**, not just what:

```
# Good
fix: skip cache check when force_file is set for single-resume re-analysis

# Bad
fix bug
```

Format: `type: short description`  
Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

### Branching

- `main` — stable, working code only
- `feature/<short-name>` — new features
- `fix/<short-name>` — bug fixes
- Never commit directly to `main` for anything non-trivial

### Pull Requests

- Open a PR before merging to `main`
- PR description must include: what changed, why, and how to test it
- At least one review before merge (from Julius or a senior team member)
- Never force-push to `main`

### What to Never Commit

- `.env` files with real values
- Credentials, tokens, passwords in any file
- Large binary files (PDFs, models, datasets) — discuss first if needed
- Output files (CSVs, logs) unless they are tracked test fixtures

---

## 7. Proposing New Tech

Any tool, library, framework, or pattern not listed in Section 2 requires a proposal PR before use.

### Process

1. Create a branch: `proposal/<tech-name>`
2. Add a file: `proposals/<tech-name>.md` using the template below
3. Open a PR and tag Julius for review
4. Do not use the proposed tech until the PR is approved and merged

### Proposal Template

```markdown
# Proposal: [Tech Name]

**Proposed by:** [Your name]  
**Date:** YYYY-MM-DD  
**PR:** #[number]

## What it is
One paragraph: what this tool/library does.

## Why we need it
What problem does it solve that existing approved tools cannot?

## Alternatives considered
List what you considered and why they don't fit.

## Risks and complexity
Be honest. Does this add complexity? What's the maintenance burden?

## How we'd use it
Concrete example: which project, which specific use case.

## Approval
- [ ] Julius Suarez
```

---

## 8. Starting a New Project — Checklist

Use this checklist every time you create a new project:

```
[ ] Created repo on DysrupIT GitHub
[ ] Initialized with `uv init`
[ ] .gitignore added (Section 5 template)
[ ] .env.example added with all required keys
[ ] .env added to .gitignore — verified
[ ] README.md created (project purpose, setup steps, how to run)
[ ] pyproject.toml and uv.lock committed
[ ] No secrets hardcoded anywhere
[ ] If using local model: quality comparison documented
[ ] First commit pushed to DysrupIT GitHub
```

---

## 9. Enforcement

These are not suggestions. If a PR introduces unapproved tech, commits secrets, or skips the `.env`/`.gitignore` standards:

1. The PR will be rejected with a comment citing the relevant section.
2. The dev must fix the issue and re-request review.

For grey areas or genuine disagreements, open a proposal PR (Section 7) rather than proceeding without approval.

---

*Questions? Raise them with Julius Suarez before writing the code.*