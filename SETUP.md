# Setup and run: macOS and Windows

The app has three local processes:

| Process | URL | Purpose |
| --- | --- | --- |
| Backend (FastAPI) | http://127.0.0.1:8000 (API docs at `/docs`) | Cases, agent, simulated ILS / CCT / OnBase / secure mail |
| Desk (Vite) | http://127.0.0.1:5173 | Correspondence desk: dashboard, case workspace, response review |
| Mailbox (Vite) | http://127.0.0.1:5176 | Borrower-side mailbox that sends the demo requests and receives replies |

No database server is needed. The backend creates and migrates a SQLite database at `.local/correspondence.sqlite3`. Both frontends forward `/api` to the backend, so **start the backend first**.

---

## 1. Prerequisites (both systems)

- **Python 3.12 or newer**
- **Node.js 22.13 or newer** (includes npm)
- **Git**, if you are cloning instead of extracting a ZIP
- An **Azure OpenAI** resource, deployment name and API key. You only need these to run the agent. The offline checks work without Azure.
- Optional: **Microsoft Edge**, only needed for the browser (Playwright) tests

Ports **8000, 5173 and 5176** must be free. The browser tests also use **8011, 5174 and 8022**.

---

## 2. macOS

### 2.1 Install the tools

Using [Homebrew](https://brew.sh):

```bash
brew install python@3.12 node git
python3.12 --version   # 3.12+
node --version         # v22.13+
```

### 2.2 One-time setup

From the project root (the folder that contains `backend/`, `frontend/` and `data/`):

```bash
# Python environment and backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python -m pip install --no-deps -e backend

# Frontend dependencies
npm --prefix frontend ci --no-fund

# Configuration (skip this if .env already exists; don't overwrite it)
[ -f .env ] || cp .env.example .env

# Database and reference catalogs
.venv/bin/python -m app.cli migrate

# Confirm the synthetic PDFs are byte-exact (prints 0 when everything is fine)
.venv/bin/python -c "from app.documents import library_problems; print(len(library_problems()))"
```

These steps do the same work as `scripts/setup.ps1` on Windows.

### 2.3 Configure Azure

Edit `.env` and fill in the values (see [section 4](#4-configure-azure-both-systems)).

### 2.4 Run

Open **three terminal tabs** in the project root and run one command in each:

```bash
# Tab 1: backend (start this first)
.venv/bin/python -m app.cli serve

# Tab 2: desk
npm --prefix frontend run dev

# Tab 3: mailbox
npm --prefix frontend run dev:mailbox
```

Then continue with [section 5](#5-use-the-app-both-systems). Press **Ctrl+C** in each tab to stop.

> Optional: running `source .venv/bin/activate` once per tab lets you type `python` instead of `.venv/bin/python`.

### 2.5 Other commands (macOS)

```bash
# Load five diagnostic cases (these don't trigger mailbox processing)
.venv/bin/python -m app.cli seed-demo
.venv/bin/python -m app.cli seed-demo --scenario DEMO-02 --variant wrong_loan --fresh

# Offline checks (no Azure calls), same as scripts/check.ps1
.venv/bin/python -m ruff check backend
.venv/bin/python -m ruff format --check backend
.venv/bin/python -m pytest backend/tests
.venv/bin/python -m app.cli check-openapi
.venv/bin/python -m app.cli check-data
npm --prefix frontend run check:api
npm --prefix frontend run build

# Browser tests (Microsoft Edge must be installed)
npm --prefix frontend run test:e2e

# After changing API schemas: regenerate the snapshot and frontend types
.venv/bin/python -m app.cli export-openapi
npm --prefix frontend run generate:api
```

The `scripts/*.ps1` helpers are written for Windows PowerShell. On macOS, use the commands above. The `.ps1` files use Windows paths (`.venv\Scripts\python.exe`, `npm.cmd`), so they won't work even under PowerShell for Mac (`pwsh`).

---

## 3. Windows

### 3.1 Install the tools

Install from the official installers, or with `winget` in PowerShell:

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Git.Git
```

When the Python installer asks, tick **"Add python.exe to PATH"**. Open a **new** PowerShell window afterwards and check the versions:

```powershell
python --version   # 3.12+
node --version     # v22.13+
```

### 3.2 Get the code

- **ZIP:** extract it into a new folder such as `C:\Projects\correspondence`. Don't run the app from inside the ZIP.
- **Git:** clone without line-ending conversion, because the synthetic PDFs are verified by SHA-256:

  ```powershell
  git clone -c core.autocrlf=false <repo-url> correspondence
  ```

### 3.3 One-time setup

Open PowerShell in the project root and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The script:

- creates `.venv`
- installs the locked Python and npm dependencies
- copies `.env.example` to `.env` if `.env` doesn't exist yet (an existing `.env` is never overwritten)
- migrates the database
- verifies the synthetic PDFs

### 3.4 Configure Azure

Edit `.env` and fill in the values (see [section 4](#4-configure-azure-both-systems)).

### 3.5 Run

Open **three PowerShell windows** in the project root and run one command in each:

```powershell
# Window 1: backend (start this first)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1

# Window 2: desk
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1

# Window 3: mailbox
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-mailbox.ps1
```

Then continue with [section 5](#5-use-the-app-both-systems). Press **Ctrl+C** in each window to stop.

If you prefer not to use the scripts, these are the direct commands:

```powershell
.\.venv\Scripts\python.exe -m app.cli serve
npm.cmd --prefix frontend run dev
npm.cmd --prefix frontend run dev:mailbox
```

### 3.6 Other commands (Windows)

```powershell
# Load five diagnostic cases
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-demo.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-demo.ps1 -Scenario DEMO-02 -Variant wrong_loan -Fresh

# Offline checks (no Azure calls); add -Browser to include Edge browser tests
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -Browser

# After changing API schemas
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export-contract.ps1

# Live Azure connectivity check (makes real Azure calls)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-azure.ps1
```

---

## 4. Configure Azure (both systems)

Set these values in `.env` at the project root. `.env` is never committed.

| Variable | Value |
| --- | --- |
| `AZURE_OPENAI_BASE_URL` | The OpenAI **v1** endpoint, which must end in `/openai/v1/`, e.g. `https://YOUR-RESOURCE.openai.azure.com/openai/v1/` |
| `AZURE_OPENAI_DEPLOYMENT` | Your deployment name. It can differ from the underlying model name. |
| `AZURE_OPENAI_API_KEY` | The resource key. It stays on the backend and is never sent to the browser. |
| `AZURE_OPENAI_REASONING_EFFORT` | Leave empty unless the deployment rejects tool calls with HTTP 400 and asks for `reasoning_effort` |

The other defaults (`APP_PORT=8000`, `APP_DATA_DIR=.local`, the agent limits) usually don't need changing. **Restart the backend after editing `.env`.**

If Azure isn't configured, mail you send is saved but stays pending. It's processed once you add the configuration and restart the backend.

---

## 5. Use the app (both systems)

1. Open the **desk** at http://127.0.0.1:5173 and type **`admin`** as the username. This signs you in as *Admin — Reviewer*; no external identity provider is needed.
2. Open the **mailbox** at http://127.0.0.1:5176 in another tab. The five prepared demo requests are in **Drafts**.
3. Open a draft (for example the amortization-schedule request, DEMO-02) and click **Send**. The backend creates the case and the Azure agent starts automatically.
4. In the desk, click the new case on the dashboard. You can follow the agent's activity, inspect **System workspaces** (Secure mail, OnBase, ILS) and review, approve, edit or return the response.
5. The reply appears back in the sender's conversation in the mailbox.

**Reset mailbox** (in the mailbox) and **Reset workspace** (in the desk account menu) both clear the cases in both apps.

---

## 6. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Port 5173 is already in use` / `address already in use` | Another copy is running. **macOS:** `lsof -nP -iTCP:5173 -sTCP:LISTEN`, then `kill <PID>`. **Windows:** `Get-NetTCPConnection -LocalPort 5173 \| Select OwningProcess`, then `Stop-Process -Id <PID>`. The Vite servers use strict ports on purpose. |
| Desk or mailbox shows network or API errors | The backend isn't running, or it's on a different port. Start it first. If you changed `APP_PORT`, restart the frontends too (they read `.env`). |
| Sending a draft never creates a case; backend logs `synthetic document(s) fail their manifest hash` | Git converted line endings in `data/`. From the project root run `git rm -r -q --cached data` then `git reset --hard`, and restart the backend. |
| Windows: `running scripts is disabled on this system` | Keep the `-ExecutionPolicy Bypass` in the commands exactly as shown. |
| Windows: `python` opens the Microsoft Store | Install Python from python.org with "Add to PATH" ticked, or turn off the *App execution aliases* for `python.exe` in Settings. |
| macOS: `python3.12: command not found` | Use `$(brew --prefix)/bin/python3.12`, or add Homebrew to your PATH (`eval "$(/opt/homebrew/bin/brew shellenv)"`). |
| Agent never starts or fails with a configuration error | Check the three Azure values in `.env`. The base URL must end in `/openai/v1/`. Then restart the backend. |
| Browser tests fail to launch | They use the installed Microsoft Edge (`channel: "msedge"`). Install Edge on either OS. |
| Want a clean start | Stop the backend and delete the `.local/` folder. It's recreated with a fresh database on the next start. |

---

## 7. Where to go next

- `README.md`: features, API and persistence details, checks
- `START_HERE.md`: moving the source package to another machine
- `plan/Mailbox_Demo_Runbook.md`: presenting the demo
- `plan/Case_Workspace_Guide.md` and `plan/Mailbox_UI_Guide.md`: UI walkthroughs
- `data/README.md`: demo scenarios and variants
