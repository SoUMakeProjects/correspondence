# Correspondence demo 0.9.0

This local Windows demo uses synthetic correspondence, two fictional clients and simulated CCT, ILS, OnBase and secure-mail systems. The configured Azure model chooses tools and executes permitted simulated actions. No real borrower messages or servicing changes are made.

Install Python 3.12+ and Node 22.13+ for Vite and PDF.js. Internet access is needed for dependencies and Azure inference. Microsoft Edge is the validated desktop browser.

Extract this archive to a new folder. From that folder, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Setup creates `.venv`, installs locked dependencies, creates a placeholder `.env` if absent and initializes a new database. It preserves any existing `.env`. Fill in the three Azure fields in `.env` using your own resource's OpenAI v1 endpoint, deployment name and key. Keep that file private. No Azure resource is created by setup.

Open three terminals in the extracted folder:

```powershell
# Terminal 1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
# Terminal 2 — case dashboard
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
# Terminal 3 — independent mailbox
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-mailbox.ps1
```

Open the case dashboard at **http://127.0.0.1:5173** and the independent mailbox at **http://127.0.0.1:5176** in separate tabs. Neither interface links to the other. For a newly built bundle, follow [the mailbox demo runbook](plan/Mailbox_Demo_Runbook.md). The earlier Phase 9 archive uses [the diagnostic runbook](plan/Demo_Runbook.md). Read [handover and troubleshooting](plan/Handover.md) and [remaining work](plan/Follow_ups.md) before presenting the scope as complete.

Type **admin** in the correspondence app's Username field to open the dashboard as **Admin — Reviewer**. The SSO login button is part of the local MVP flow; no external identity provider or password is used. There is no registration or role creation. Refresh preserves the current tab's session, and Sign out returns to login. Mailbox opens directly.

Optional: run `scripts/seed-demo.ps1` to load all five starting cases. Repeating it reuses those cases; `-Fresh` creates isolated new instances and preserves history. Use the UI to supply information on an existing case and resume it. Stop servers with Ctrl+C and restart using the same commands; retain `.local` for previous case history and PDFs.

This runtime bundle includes a SHA-256 manifest, application source, locked dependencies, synthetic inputs, migration files and presenter guides. It excludes the private Office source documents, their path registry, credentials, existing databases, acceptance artifacts and development/browser tests. Original-source reconciliation and the full engineering suite run from the original development workspace. Do not run `rebuild-data` or `check-data` from this bundle: those maintenance commands require the excluded source files. Normal startup, scenario loading, build and live workflow/recovery checks do not require them.

To check the frontend build, run `npm.cmd --prefix frontend run build`. Optional scripts `test-azure.ps1`, `test-workflow.ps1` and `test-recovery.ps1` make real Azure requests and save isolated evaluation artifacts under `.local`; they incur model usage. No production deployment, identity management, retention policy or real-system integration is included.
