# Set up this source package on another machine

This ZIP contains the complete application source, backend and browser tests, database migrations, dependency lockfiles, demo fixtures, reference documents, BRD, coding plan, checkpoints, runbooks and UI reference images. The packaging scripts are included so you can create another ZIP after making changes.

## 1. Extract and install

Use a new folder, such as `C:\Projects\correspondence`. Do not run the application from inside the ZIP or extract over another running copy.

Install **Python 3.12 or newer** and **Node.js 22.13 or newer**, with both available on PATH. Windows and Microsoft Edge are the validated environment. An internet connection is needed to install dependencies and use Azure.

Open PowerShell in the extracted project folder and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Setup creates `.venv`, installs Python and frontend dependencies, creates `.env` from `.env.example` if needed, and initializes a new local database. It does not overwrite an existing `.env`.

## 2. Configure Azure

Fill these values in the new machine's `.env`:

- `AZURE_OPENAI_BASE_URL`: your resource's OpenAI v1 endpoint.
- `AZURE_OPENAI_DEPLOYMENT`: your deployed model's deployment name.
- `AZURE_OPENAI_API_KEY`: your resource key.

The shared ZIP includes only the blank configuration template. Existing credentials, case databases, uploads, browser sessions, build output, caches and installed dependencies are excluded. Copy any credentials separately using your normal secure process.

## 3. Start the application

Open three PowerShell terminals in the extracted project folder. Run one command in each:

```powershell
# Terminal 1: backend
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1

# Terminal 2: correspondence app
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1

# Terminal 3: mailbox
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-mailbox.ps1
```

Open **http://127.0.0.1:5173**. Type **admin** in Username to enter as **Admin — Reviewer**. The SSO login button belongs to the local MVP flow; no external identity provider is required.

Open **http://127.0.0.1:5176** separately for Mailbox. Its five prepared requests are in Drafts. Sending a request starts the Azure agent. The new machine starts without the original machine's case history. Press **Ctrl+C** in each server terminal to stop it.

## 4. Read the relevant documents

- `README.md`: application features and technical commands.
- `plan/Business_Requirements_Document.md`: business requirements.
- `plan/Coding_Plan_and_Checkpoints.md`: implementation phases.
- `plan/Mailbox_Demo_Runbook.md`: presentation instructions.
- `plan/Mailbox_UI_Guide.md`: drafts, editing, attachments and previews.
- `plan/Case_Workspace_Guide.md`: login, dashboard and case review.
- `plan/Demo_Flows_and_System_Connections.md`: demo flows in simple English.
- `plan/Handover.md` and `plan/Follow_ups.md`: handover and remaining work.
- `docs/`: original process documents and samples, with the workbook redactions below.

## Reference workbook redactions

`docs/Inquiry_Responses_Extracted_Pro.xlsx` is a values-only sharing copy. The known credential-bearing row 474 and internal sender configuration rows 475–483 are redacted. Any other row containing a credential-assignment marker is also redacted. The export contains no workbook comments, hyperlinks, embedded images or external links. The source reconciliation artifacts in `data/knowledge/` are regenerated against this shared copy, so source checks work after extraction. Originals on the packaging machine are unchanged. `PACKAGE_INFO.json` lists the redacted sheet and row numbers without their original contents.

OneNote index files, Office temporary lock files, editor/agent settings and local runtime artifacts are not needed to develop or run this application and are excluded. Historical docs can mention `.local` screenshots and live-test reports; those machine-specific artifacts are not included.

## Check or rebuild the package

After setup, run the offline checks from the project folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

Add `-Browser` for browser tests with Microsoft Edge installed. The ordinary checks do not call Azure; scripts explicitly named `test-azure`, `test-agent`, `test-workflow`, `test-recovery` and `test-mailbox` can make live calls.

To create a new source ZIP:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package-source.ps1

# Optional explicit destination; existing ZIP files are never overwritten.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package-source.ps1 -OutputPath .\correspondence-source.zip
```

The default output is a timestamped ZIP in `.local/releases/`, with a companion `.zip.sha256` checksum. It includes `PACKAGE_MANIFEST.json`, which records the SHA-256 hash of every packaged file. ZIP contents and hashes are verified before success is reported. The existing `package-demo.ps1` produces a smaller runtime bundle; use `package-source.ps1` for code and documentation handover.

To verify a received source ZIP after installing dependencies:

```powershell
.\.venv\Scripts\python.exe .\scripts\package_source.py --verify .\correspondence-source.zip
```
