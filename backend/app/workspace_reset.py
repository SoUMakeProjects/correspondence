"""Demo reset shared by the Correspondence Desk and the Mailbox.

Either app can reset the workspace. The reset removes every case and its mail,
runs, drafts, deliveries and documents, which returns the workspace to its
base state after setup. Reference catalogs (taxonomy, source manifest, client
configurations and curated knowledge) are left alone: the application never
changes them.

Each reset gets a new generation id. Both apps poll it and reset their own
screens when it changes, so a reset in one app is reflected in the other.
"""

import json
import shutil
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.db import Base

router = APIRouter(prefix="/api/workspace", tags=["System"])

CATALOG_TABLES = {
    "taxonomy_entries",
    "source_manifest_entries",
    "client_configurations",
    "knowledge_items",
}
STATE_FILE = "workspace-reset.json"


class ResetState(BaseModel):
    generation: str
    reset_at: datetime | None = None


def read_state(settings) -> ResetState:
    try:
        return ResetState.model_validate_json(
            (settings.data_dir / STATE_FILE).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        # Never reset since setup.
        return ResetState(generation="initial")


def reset_workspace(sessions, settings) -> ResetState:
    runtime = [t for t in reversed(Base.metadata.sorted_tables) if t.name not in CATALOG_TABLES]
    with sessions() as session:
        # Take the write lock first so worker threads cannot interleave writes.
        session.execute(text("BEGIN IMMEDIATE"))
        for table in runtime:  # children before parents
            session.execute(table.delete())
        session.commit()
    # Stored evidence, uploads and response packages belong to the deleted cases.
    documents = settings.data_dir / "documents"
    if documents.is_dir():
        for entry in documents.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
    state = ResetState(generation=str(uuid4()), reset_at=datetime.now(timezone.utc))
    (settings.data_dir / STATE_FILE).write_text(
        json.dumps(state.model_dump(mode="json")), encoding="utf-8"
    )
    return state


@router.get("/reset", response_model=ResetState)
def reset_state(request: Request):
    return read_state(request.app.state.settings)


@router.post("/reset", response_model=ResetState)
def reset(request: Request):
    return reset_workspace(request.app.state.sessions, request.app.state.settings)
