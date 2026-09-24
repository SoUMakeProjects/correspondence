from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import CaseRead
from app.workflow import acknowledge, edit_response, ingest, workspace
from app.workflow_contracts import CaseInput, DraftEdit, HandoffAcknowledge, WorkflowRead

router = APIRouter(prefix="/api", tags=["Case workflow"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/cases/{case_id}/workflow", response_model=WorkflowRead)
def read_workflow(case_id: UUID, request: Request, session: SessionDep):
    return workspace(session, request.app.state.settings.data_dir, str(case_id))


@router.post("/cases/{case_id}/inputs", response_model=CaseRead)
def supply_input(case_id: UUID, payload: CaseInput, request: Request, session: SessionDep):
    return ingest(session, request.app.state.settings.data_dir, str(case_id), payload)


@router.post("/cases/{case_id}/draft-edits", response_model=dict)
def edit_draft(case_id: UUID, payload: DraftEdit, request: Request, session: SessionDep):
    return edit_response(session, request.app.state.settings.data_dir, str(case_id), payload)


@router.post("/cases/{case_id}/handoff-acknowledgments", response_model=dict)
def acknowledge_handoff(
    case_id: UUID, payload: HandoffAcknowledge, request: Request, session: SessionDep
):
    return acknowledge(session, request.app.state.settings.data_dir, str(case_id), payload)
