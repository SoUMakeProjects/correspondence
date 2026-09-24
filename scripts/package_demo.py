"""Build a local demo bundle from an explicit allowlist; never include local data or .env."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
TREES = {
    "backend/app": {".py"},
    "backend/migrations": {".py", ".mako"},
    "data": {".json", ".pdf"},
    "frontend/src": {".ts", ".tsx", ".css", ".svg"},
    "frontend/public": {".svg", ".png", ".ico"},
}
FILES = [
    ".env.example",
    "backend/pyproject.toml",
    "backend/requirements.lock",
    "backend/openapi.json",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/index.html",
    "frontend/main.tsx",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "frontend/vite.mailbox.config.ts",
    "frontend/mailbox/index.html",
    "frontend/mailbox/main.tsx",
    "scripts/setup.ps1",
    "scripts/start-backend.ps1",
    "scripts/start-frontend.ps1",
    "scripts/start-mailbox.ps1",
    "scripts/seed-demo.ps1",
    "scripts/test-azure.ps1",
    "scripts/test-workflow.ps1",
    "scripts/test-recovery.ps1",
    "scripts/test-mailbox.ps1",
    "plan/Demo_Runbook.md",
    "plan/Mailbox_Demo_Runbook.md",
    "plan/Mailbox_UI_Guide.md",
    "plan/Case_Workspace_Guide.md",
    "plan/Demo_Flows_and_System_Connections.md",
    "plan/checkpoints/PH-10.md",
    "plan/checkpoints/UI-REFRESH.md",
    "plan/checkpoints/UI-DASHBOARD.md",
    "plan/checkpoints/MAILBOX-UI.md",
    "plan/checkpoints/MAILBOX-CUSTOM.md",
    "plan/checkpoints/MAILBOX-PDF.md",
    "plan/checkpoints/MAILBOX-LAPTOP.md",
    "plan/checkpoints/MAILBOX-EDITS-IMAGES.md",
    "plan/checkpoints/LOGIN-MVP.md",
    "plan/Handover.md",
    "plan/Follow_ups.md",
]


def main():
    entries = {name: ROOT / name for name in FILES}
    entries["README.md"] = ROOT / "plan/Package_Readme.md"
    for directory, suffixes in TREES.items():
        for path in (ROOT / directory).rglob("*"):
            if (
                path.is_file()
                and path.suffix in suffixes
                and "__pycache__" not in path.parts
            ):
                entries[path.relative_to(ROOT).as_posix()] = path
    # Original source registry is maintenance-only and names private source-file paths.
    entries.pop("data/knowledge/source_registry.v1.json", None)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = (
        ROOT / ".local" / "releases" / f"correspondence-demo-0.9.0-{stamp}.zip"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, path in entries.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Package input is missing or is a link: {name}")
    with ZipFile(destination, "x", compression=ZIP_DEFLATED) as archive:
        for name, path in sorted(entries.items()):
            content = path.read_bytes()
            manifest[name] = hashlib.sha256(content).hexdigest()
            archive.writestr(name, content)
        archive.writestr("PACKAGE_MANIFEST.json", json.dumps(manifest, indent=2))
    report = {
        "version": "0.9.0",
        "path": str(destination),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "file_count": len(manifest),
        "source_documents_included": False,
        "credentials_or_runtime_data_included": False,
    }
    (ROOT / ".local" / "phase9-package.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
